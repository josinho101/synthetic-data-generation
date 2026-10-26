"""Compute landmark positions on the fitted body and add them as non-deforming rig bones.

LM_<anchor> surface points, LM_<level>_surf / LM_<level> spine points (vertebral bodies oriented
along the spine) and AN_<frame> anatomical frames (skull, thorax, pelvis, scapula_L/R).
Oriented bones: Y superior (along the bone), Z subject right, X anterior.
"""

import logging

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import anatomy_rules
from .. import landmark_math as lm
from .. import landmark_rules
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
    points, centres = {}, []
    emit = set(spine.get("emit", ["internal", "surface"]))
    lo, hi = geometry.body_extent(coords, body_indices)
    for level in spine["levels"]:
        surface = Vector(lm.point_at_arc(profile, arc[level]))
        depth = _ap_depth(bvh, surface)
        offset = internal_offset_m(spine["internal_depth"][lm.region_of(level)], depth, hi - lo)
        if "surface" in emit:
            points[f"{level}_surf"] = {"position": surface, "kind": "surface", "level": level}
        centres.append(tuple(surface + ANTERIOR * offset))
        if "internal" in emit:
            points[level] = {"position": surface + ANTERIOR * offset, "kind": "internal", "level": level,
                             "ap_depth_m": round(depth, 4), "internal_offset_m": round(offset, 4)}
    for level, axes in zip(spine["levels"], landmark_rules.spine_axes(centres)):
        if level in points:
            points[level]["axes"] = axes
    return points


def apply_spine_shape(points: dict, levels: list, cfg: dict, subject: dict) -> dict:
    """Reshape the vertebral bodies to the patient's sampled kyphosis / lordosis / scoliosis."""
    centres = [np.array(tuple(points[lv]["position"])) for lv in levels]
    before = anatomy_rules.spine_curvature(centres, levels)
    rng = np.random.default_rng(int(subject.get("seed", 0)) + 7919)
    shape = anatomy_rules.sample_spine_shape(rng, float(subject.get("age", 40)), cfg)
    new, axial = anatomy_rules.reshape_spine(centres, levels, shape)
    for level, c, axes, deg in zip(levels, new, landmark_rules.spine_axes(new), axial):
        a = np.radians(deg)
        rot_y = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        points[level]["position"] = Vector(tuple(c))
        points[level]["axes"] = axes @ rot_y
    return {"target": shape, "before": before, "after": anatomy_rules.spine_curvature(new, levels)}


def compute_landmarks(basemesh, cfg: dict, subject: dict = None) -> tuple:
    """-> (points, spine shape) for anchors, spine levels, frames and derived joints."""
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
    shape = None
    if (cfg.get("spine_shape") or {}).get("enabled"):
        shape = apply_spine_shape(points, cfg["spine"]["levels"], cfg["spine_shape"], subject or {})
    wanted = lm.expand_parent_map((cfg.get("frames") or {}).get("parents", {}), [])
    rest = {name: np.array(tuple(info["position"])) for name, info in points.items()}
    for name, (origin, axes) in landmark_rules.anatomical_frames(rest).items():
        if anatomy_rules.parent_lookup(name, wanted):
            points[f"frame:{name}"] = {"position": Vector(tuple(origin)), "kind": "frame", "frame": name, "axes": axes}
    skin = np.array([tuple(coords[i]) for i in body_indices])
    lo, hi = geometry.body_extent(coords, body_indices)
    for name, info in anatomy_rules.derived_joints(rest, skin, hi - lo).items():
        info = dict(info, position=Vector(tuple(info["position"])))
        if info["kind"] == "frame":
            if anatomy_rules.parent_lookup(info["frame"], wanted):
                points[f"frame:{info['frame']}"] = info
        else:
            points[name] = info
    return points, shape


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
    return anatomy_rules.parent_lookup(name, parents) or parents.get(info.get("level", "")) or "root"


def add_landmark_bones(armature, points: dict, cfg: dict) -> dict:
    """Create LM_* / AN_* bones (use_deform=False) parented to the configured rig bones."""
    parents = lm.expand_parent_map(cfg["parent_bones"], cfg["spine"]["levels"])
    frames = cfg.get("frames") or {}
    frame_parents = lm.expand_parent_map(frames.get("parents", {}), [])
    prefix, length = cfg.get("bone_prefix", "LM_"), float(cfg.get("bone_length_m", 0.02))
    frame_prefix = frames.get("prefix", "AN_")
    to_local = armature.matrix_world.inverted()
    rot = to_local.to_3x3()
    bpy.context.view_layer.objects.active = armature
    for obj in bpy.context.view_layer.objects:
        obj.select_set(obj == armature)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature.data.edit_bones
    result = {}
    try:
        for name, info in points.items():
            head = to_local @ info["position"]
            if info["kind"] == "frame":
                bone_name = f"{frame_prefix}{info['frame']}"
                parent_name = anatomy_rules.parent_lookup(info["frame"], frame_parents, "root")
            else:
                bone_name, parent_name = f"{prefix}{name}", _parent_for(name, parents, info)
            if parent_name == "auto_axial":
                parent_name = _nearest_axial(edit_bones, head)
            parent = edit_bones.get(parent_name)
            if parent is None:
                _LOG.warning(f"parent bone {parent_name} missing for {name}; using root")
                parent, parent_name = edit_bones.get("root"), "root"
            bone = edit_bones.new(bone_name)
            axes = info.get("axes")
            if axes is None:
                bone.head, bone.tail = head, head + Vector((0.0, 0.0, length))
            else:                                                   # Y along the bone, roll puts Z to the right
                bone.head, bone.tail = head, head + (rot @ Vector(tuple(axes[:, 1]))).normalized() * length
                bone.align_roll(rot @ Vector(tuple(axes[:, 2])))
            bone.parent, bone.use_connect, bone.use_deform = parent, False, False
            result[name] = {**{k: v for k, v in info.items() if k not in ("position", "axes")},
                            "bone": bone.name, "parent": parent_name,
                            "rest_position_m": [round(c, 5) for c in info["position"]]}
            if axes is not None:
                result[name]["axes_xyz"] = np.round(np.asarray(axes).T, 5).tolist()
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    _LOG.info(f"added {len(result)} landmark bones")
    return result
