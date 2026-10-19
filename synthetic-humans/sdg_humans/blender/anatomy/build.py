"""Build the anatomical skeleton for one human: one skinned mesh per bone, parented to the rig."""

import logging

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import bake, colors, geometry, preview
from ..gown.profile import is_profile_bone
from ..gown.regions import dominant_bones
from . import appendicular, axial

_LOG = logging.getLogger("sdg_humans.blender.anatomy")

PARTS = {
    "skull": axial.skull, "vertebrae": axial.vertebrae, "ribs": axial.ribs, "sternum": axial.sternum,
    "shoulder_girdle": appendicular.shoulder_girdle, "pelvis": appendicular.pelvis,
    "limbs": appendicular.limbs, "hands_feet": appendicular.hands_feet,
}


def _context(basemesh, armature, landmarks: dict, levels: list, stature_m: float, cfg: dict) -> dict:
    coords = geometry.evaluated_coords(basemesh)
    body = geometry.group_vertex_indices(basemesh, "body")
    dom = dominant_bones(basemesh, {b.name for b in armature.data.bones})
    keep = {i for i in body if is_profile_bone(dom.get(i)) or str(dom.get(i)).startswith("neck")}
    polys = [list(p.vertices) for p in basemesh.data.polygons if all(v in keep for v in p.vertices)]
    bvh = BVHTree.FromPolygons([tuple(c) for c in coords], polys)
    midline = [coords[i] for i in body if abs(coords[i].x) < 0.01]
    s = stature_m / 1.70
    world = armature.matrix_world
    bones = armature.data.bones

    def front_y_at(z):
        ys = [c.y for c in midline if abs(c.z - z) < 0.012]
        return min(ys) if ys else -0.1

    def back_point(x, z):
        origin = Vector((x, front_y_at(z) + 0.04, z))
        hit = bvh.ray_cast(origin, Vector((0, 1, 0)), 1.0)[0]
        return hit - Vector((0, 1, 0)) * max(float(cfg["soft_tissue_cm"]) / 100.0 * s, 0.01) if hit else None

    return {
        "cfg": cfg, "s": s, "levels": levels, "bones": [b.name for b in bones],
        "lm": {name: Vector(info["rest_position_m"]) for name, info in landmarks.items()},
        "lm_parent": {name: info["parent"] for name, info in landmarks.items()},
        "head": lambda n: world @ bones[n].head_local, "tail": lambda n: world @ bones[n].tail_local,
        "lateral": lambda n: (world.to_3x3() @ bones[n].matrix_local.to_3x3().col[0]).normalized(),
        "torso_bvh": bvh, "front_y_at": front_y_at, "back_point": back_point,
        "soft_tissue_m": float(cfg["soft_tissue_cm"]) / 100.0 * s,
        "soft_tissue_fraction": float(cfg.get("soft_tissue_fraction", 0.08)),
    }


def keep_inside(acc, body_bvh, margin_m: float) -> int:
    """Pull every bone vertex at least margin_m inside the skin (no bone ever shows through)."""
    moved = 0
    for k, co in enumerate(acc.verts):
        p = Vector(co)
        loc, normal, _i, dist = body_bvh.find_nearest(p)
        if loc is None:
            continue
        outside = (p - loc).dot(normal) > 0
        if outside or dist < margin_m:
            acc.verts[k] = tuple(loc - normal * margin_m)
            moved += 1
    return moved


def build_skeleton(basemesh, armature, landmarks: dict, levels: list, stature_m: float, cfg: dict,
                   human_id: str) -> list:
    """Returns metadata entries [{name, object, rig_bone, vertices}] for every bone mesh."""
    ctx = _context(basemesh, armature, landmarks, levels, stature_m, cfg)
    material = bake.simple_material(f"{human_id}_bone", color=colors.hex_to_linear_rgba(cfg.get("color_rgb", "#e3d8c3")),
                                    roughness=0.6)
    coords = geometry.evaluated_coords(basemesh)
    body = set(geometry.group_vertex_indices(basemesh, "body"))
    body_bvh = BVHTree.FromPolygons([tuple(c) for c in coords], [list(p.vertices) for p in basemesh.data.polygons
                                                                 if all(v in body for v in p.vertices)])
    margin = float(cfg.get("min_depth_below_skin_cm", 0.4)) / 100.0
    created = []
    for part in cfg.get("parts", list(PARTS)):
        try:
            pieces = PARTS[part](ctx)
        except (KeyError, ValueError) as exc:
            _LOG.warning(f"anatomy part {part} skipped: {exc}")
            continue
        for name, piece in pieces.items():
            acc, rig_bone = piece[0], piece[1]
            thickness = piece[2] if len(piece) > 2 else None
            if not acc.faces:
                continue
            pulled = keep_inside(acc, body_bvh, margin)
            if pulled:
                _LOG.debug(f"bone {name}: {pulled} vertices pulled inside the skin")
            obj = acc.to_object(f"bone_{name}", material, armature)
            if thickness:
                solid = obj.modifiers.new("BoneThickness", "SOLIDIFY")
                solid.thickness, solid.offset = thickness, 0.0
            created.append({"name": name, "object": obj.name, "rig_bone": rig_bone, "part": part,
                            "vertices": len(obj.data.vertices)})
    _LOG.info(f"anatomical skeleton: {len(created)} bone meshes")
    return created


def render_skeleton_preview(path, stature_m: float, preview_cfg: dict, bone_objects: list) -> None:
    """Front + side render of the bone meshes only (other meshes hidden for the render)."""
    names = {entry["object"] for entry in bone_objects}
    hidden = []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name not in names and not obj.hide_render:
            obj.hide_render = True
            hidden.append(obj)
    try:
        preview.render_preview(path, stature_m, preview_cfg)
    finally:
        for obj in hidden:
            obj.hide_render = False
