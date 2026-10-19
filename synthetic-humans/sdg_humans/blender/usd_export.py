"""Prepare the rigged human for USD and export it (UsdSkel, meters, Z-up, preview surfaces)."""

import logging
import re
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

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


_INSIDE_RAYS = [Vector(d) for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, -1))]


def _cover_bvh(objects):
    """World-space BVH of the (evaluated) covering garments, e.g. shoes."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        offset = len(verts)
        verts += [tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices]
        polys += [[offset + i for i in p.vertices] for p in mesh.polygons]
        evaluated.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys) if polys else None


def finalize_basemesh(ns, basemesh, hide_groups=(), cover_objects=()) -> None:
    """Bake shape keys, drop the masks and delete helper / joint-cube geometry. Body vertices of the
    delete groups in `hide_groups` (feet under shoes) are deleted only where they are really inside
    a `cover_objects` mesh (rays in all horizontal directions and downwards hit it), so low shoes
    never leave a hole at the ankle."""
    if basemesh.data.shape_keys:
        ns.TargetService.bake_targets(basemesh)
    for modifier in list(basemesh.modifiers):
        if modifier.type == "MASK":
            basemesh.modifiers.remove(modifier)
    helper_groups = {g.index for g in basemesh.vertex_groups if g.name in ("HelperGeometry", "JointCubes")}
    hide_indices = {g.index for g in basemesh.vertex_groups if g.name in set(hide_groups)}
    cover = _cover_bvh(cover_objects) if hide_indices and cover_objects else None
    matrix = basemesh.matrix_world

    def inside_cover(co):
        origin = matrix @ co
        return all(cover.ray_cast(origin, d, 0.4)[0] is not None for d in _INSIDE_RAYS)

    bm = bmesh.new()
    bm.from_mesh(basemesh.data)
    deform = bm.verts.layers.deform.active
    doomed, hidden = [], 0
    for v in bm.verts:
        if not deform:
            break
        groups = v[deform]
        if any(gi in groups and groups[gi] > 0.5 for gi in helper_groups):
            doomed.append(v)
        elif cover and any(gi in groups and groups[gi] > 0.5 for gi in hide_indices) and inside_cover(v.co):
            doomed.append(v)
            hidden += 1
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(basemesh.data)
    bm.free()
    _LOG.info(f"basemesh finalised: {len(basemesh.data.vertices)} vertices after removing helpers "
              f"({hidden} body vertices inside shoes removed)")


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
