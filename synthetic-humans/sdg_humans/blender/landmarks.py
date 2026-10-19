"""Compute landmark positions on the fitted body and add them as non-deforming rig bones."""

import logging

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import landmark_math as lm
from . import geometry

_LOG = logging.getLogger("sdg_humans.blender.landmarks")

ANTERIOR = Vector((0.0, -1.0, 0.0))  # MPFB humans face -Y


def _body_bvh(basemesh, coords, body_indices):
    keep = set(body_indices)
    polys = [list(p.vertices) for p in basemesh.data.polygons if all(v in keep for v in p.vertices)]
    return BVHTree.FromPolygons([tuple(c) for c in coords], polys)


def _ap_depth(bvh, point: Vector, fallback=0.12) -> float:
    origin = point + ANTERIOR * 0.002
    hit, _normal, _index, distance = bvh.ray_cast(origin, ANTERIOR, 1.0)
    return (distance + 0.002) if hit is not None else fallback


def internal_offset_m(rule: dict, ap_depth: float, stature_m: float) -> float:
    if "fixed_cm" in rule:
        scale = stature_m / 1.70 if rule.get("scale_with_stature") else 1.0
        return float(rule["fixed_cm"]) / 100.0 * scale
    return ap_depth * float(rule["fraction"])


def spine_points(basemesh, coords, cfg: dict, anchors: dict, bvh, body_indices) -> dict:
    spine = cfg["spine"]
    top = coords[anchors[spine["top_anchor"]]]
    bottom = coords[anchors[spine["bottom_anchor"]]]
    midline = [tuple(coords[i]) for i in body_indices if abs(coords[i].x) < 0.006]
    chain = [tuple(top), tuple(bottom)] + [tuple(coords[anchors[a]]) for a in spine["pins"].values()]
    profile = lm.posterior_profile(midline, chain, max_forward_m=float(spine.get("max_forward_cm", 4.0)) / 100.0)
    pins = {level: lm.project_to_arc(profile, tuple(coords[anchors[a]])) for level, a in spine["pins"].items()}
    s_top = lm.project_to_arc(profile, tuple(top)) + float(spine.get("top_offset_cm", 0.0)) / 100.0
    arc = lm.distribute_levels(spine["levels"], spine["segment_ratios"], pins,
                               s_top, lm.project_to_arc(profile, tuple(bottom)))
    points = {}
    emit = set(spine.get("emit", ["internal", "surface"]))
    lo, hi = geometry.body_extent(coords, body_indices)
    for level in spine["levels"]:
        surface = Vector(lm.point_at_arc(profile, arc[level]))
        depth = _ap_depth(bvh, surface)
        offset = internal_offset_m(spine["internal_depth"][lm.region_of(level)], depth, hi - lo)
        if "surface" in emit:
            points[f"{level}_surf"] = {"position": surface, "kind": "surface", "level": level}
        if "internal" in emit:
            points[level] = {"position": surface + ANTERIOR * offset, "kind": "internal", "level": level,
                             "ap_depth_m": round(depth, 4), "internal_offset_m": round(offset, 4)}
    return points


def compute_landmarks(basemesh, cfg: dict) -> dict:
    anchors = cfg["anchors"]
    missing = [k for k, v in anchors.items() if v is None]
    if missing:
        raise ValueError(f"landmark anchors not calibrated: {missing} (run scripts/calibrate_anchors.py)")
    coords = geometry.evaluated_coords(basemesh)
    body_indices = geometry.group_vertex_indices(basemesh, "body")
    bvh = _body_bvh(basemesh, coords, body_indices)
    points = {name: {"position": coords[idx].copy(), "kind": "anchor", "vertex": idx}
              for name, idx in anchors.items()}
    points.update(spine_points(basemesh, coords, cfg, anchors, bvh, body_indices))
    return points


AXIAL_CHAIN = ("root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "neck02", "neck03", "head")


def _segment_distance(p, a, b) -> float:
    ab = b - a
    t = max(0.0, min(1.0, (p - a).dot(ab) / max(ab.length_squared, 1e-12)))
    return (p - (a + ab * t)).length


def _nearest_axial(edit_bones, point) -> str:
    """Axial-chain bone whose head->tail segment is closest to the point (armature space)."""
    candidates = [b for b in (edit_bones.get(n) for n in AXIAL_CHAIN) if b is not None]
    return min(candidates, key=lambda b: _segment_distance(point, b.head, b.tail)).name


def _parent_for(name: str, parents: dict, info: dict) -> str:
    return parents.get(name) or parents.get(info.get("level", "")) or "root"


def add_landmark_bones(armature, points: dict, cfg: dict) -> dict:
    """Create LM_* bones (use_deform=False) parented to the configured rig bones."""
    parents = lm.expand_parent_map(cfg["parent_bones"], cfg["spine"]["levels"])
    prefix, length = cfg.get("bone_prefix", "LM_"), float(cfg.get("bone_length_m", 0.02))
    to_local = armature.matrix_world.inverted()
    bpy.context.view_layer.objects.active = armature
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj == armature)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    result = {}
    try:
        for name, info in points.items():
            head = to_local @ info["position"]
            parent_name = _parent_for(name, parents, info)
            if parent_name == "auto_axial":
                parent_name = _nearest_axial(edit_bones, head)
            parent = edit_bones.get(parent_name)
            if parent is None:
                _LOG.warning(f"parent bone {parent_name} missing for {name}; using root")
                parent, parent_name = edit_bones.get("root"), "root"
            bone = edit_bones.new(f"{prefix}{name}")
            bone.head, bone.tail = head, head + Vector((0.0, 0.0, length))
            bone.parent, bone.use_connect, bone.use_deform = parent, False, False
            result[name] = {**{k: v for k, v in info.items() if k != "position"},
                            "bone": bone.name, "parent": parent_name,
                            "rest_position_m": [round(c, 5) for c in info["position"]]}
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    _LOG.info(f"added {len(result)} landmark bones")
    return result
