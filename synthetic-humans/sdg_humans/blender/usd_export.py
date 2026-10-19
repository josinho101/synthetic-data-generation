"""Prepare the rigged human for USD and export it (UsdSkel, meters, Z-up, preview surfaces)."""

import logging
import re
from pathlib import Path

import bmesh
import bpy

_LOG = logging.getLogger("sdg_humans.blender.usd_export")


def usd_name(name: str) -> str:
    """Blender's USD exporter turns characters such as '.' into '_' in prim/joint names."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return f"_{name}" if name[:1].isdigit() else name


def joint_path(bone) -> str:
    """UsdSkel joint path of a Blender bone, e.g. 'root/spine05/LM_T1'."""
    names = []
    while bone is not None:
        names.append(usd_name(bone.name))
        bone = bone.parent
    return "/".join(reversed(names))


def _select(objects, active) -> None:
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj in objects)
    bpy.context.view_layer.objects.active = active


def finalize_basemesh(ns, basemesh, hide_groups=()) -> None:
    """Bake shape keys, drop the masks and delete helper / joint-cube geometry, plus the body
    vertices hidden by the delete groups in `hide_groups` (e.g. feet inside shoes)."""
    if basemesh.data.shape_keys:
        ns.TargetService.bake_targets(basemesh)
    for modifier in list(basemesh.modifiers):
        if modifier.type == "MASK":
            basemesh.modifiers.remove(modifier)
    doomed_names = {"HelperGeometry", "JointCubes"} | set(hide_groups)
    helper_groups = {g.index for g in basemesh.vertex_groups if g.name in doomed_names}
    bm = bmesh.new()
    bm.from_mesh(basemesh.data)
    deform = bm.verts.layers.deform.active
    doomed = [v for v in bm.verts if deform and any(gi in v[deform] and v[deform][gi] > 0.5 for gi in helper_groups)]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(basemesh.data)
    bm.free()
    _LOG.info(f"basemesh finalised: {len(basemesh.data.vertices)} vertices after removing helpers")


def apply_non_armature_modifiers(obj) -> None:
    _select([obj], obj)
    for modifier in list(obj.modifiers):
        if modifier.type != "ARMATURE":
            bpy.ops.object.modifier_apply(modifier=modifier.name)


def clean_weights(obj, bone_names: set, max_influences: int) -> None:
    """Keep only bone weight groups, limit influences per vertex and normalise."""
    for group in list(obj.vertex_groups):
        if group.name not in bone_names:
            obj.vertex_groups.remove(group)
    if not obj.vertex_groups:
        return
    _select([obj], obj)
    bpy.ops.object.vertex_group_limit_total(group_select_mode="ALL", limit=max_influences)
    bpy.ops.object.vertex_group_normalize_all(group_select_mode="ALL", lock_active=False)


def export_usd(armature, path: Path, human_id: str, usd_cfg: dict) -> Path:
    meshes = [obj for obj in armature.children_recursive if obj.type == "MESH"]
    deform_bones = {b.name for b in armature.data.bones if b.use_deform}
    for obj in meshes:
        apply_non_armature_modifiers(obj)
        clean_weights(obj, deform_bones, int(usd_cfg.get("max_bone_influences", 4)))
        if usd_cfg.get("triangulate"):
            _select([obj], obj)
            bpy.ops.object.modifier_add(type="TRIANGULATE")
            bpy.ops.object.modifier_apply(modifier=obj.modifiers[-1].name)
    _select(meshes + [armature], armature)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.usd_export(
        filepath=str(path),
        selected_objects_only=True,
        export_animation=False,
        export_uvmaps=True,
        export_normals=True,
        export_materials=True,
        generate_preview_surface=True,
        export_textures_mode="KEEP" if usd_cfg.get("export_textures", True) else "NONE",
        relative_paths=bool(usd_cfg.get("relative_paths", True)),
        export_armatures=True,
        only_deform_bones=False,  # keep the non-deforming LM_* landmark joints
        export_shapekeys=False,
        export_global_up_selection="Z",
        export_global_forward_selection="NEGATIVE_Y",
        convert_scene_units="METERS",
        meters_per_unit=float(usd_cfg.get("meters_per_unit", 1.0)),
        root_prim_path=f"/{human_id}",
        export_custom_properties=False,
        export_lights=False,
        export_cameras=False,
        convert_world_material=False,
        triangulate_meshes=False,
    )
    cutouts = {usd_name(m.name) for obj in meshes for m in obj.data.materials if m and m.get("sdg_alpha_cutout")}
    if cutouts:
        _set_opacity_threshold(path, cutouts)
    _LOG.info(f"USD written: {path} ({len(meshes)} meshes)")
    return path


def _set_opacity_threshold(path: Path, material_names: set, threshold: float = 0.5) -> None:
    """Alpha cut-out for hair / lace: UsdPreviewSurface opacityThreshold (Blender bundles pxr)."""
    from pxr import Sdf, Usd, UsdShade
    stage = Usd.Stage.Open(str(path))
    for prim in stage.Traverse():
        if prim.IsA(UsdShade.Material) and prim.GetName() in material_names:
            for child in Usd.PrimRange(prim):
                if child.GetAttribute("info:id").Get() == "UsdPreviewSurface":
                    child.CreateAttribute("inputs:opacityThreshold", Sdf.ValueTypeNames.Float).Set(threshold)
    stage.GetRootLayer().Save()
