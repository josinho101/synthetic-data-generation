"""Compute landmark positions on the fitted rest body and turn them into non-deforming skeleton joints.

LM_<anchor> surface points (MPFB hm08 vertex IDs, configs/landmarks.yaml), LM_<level>_surf / LM_<level> spine points
(vertebral bodies oriented along the spine), AN_<frame> anatomical frames (skull, thorax, pelvis, scapula_L/R) and
the derived joints of anatomy_rules.py. Port of the MPFB Blender version (sdg_humans/blender/landmarks.py):
same rules, numpy + MeshBVH instead of bpy. Oriented joints: Y superior, Z subject right, X anterior.
"""

import logging

import numpy as np

from . import anatomy_rules
from . import landmark_math as lm
from . import landmark_rules
from .geometry import MeshBVH

_LOG = logging.getLogger("anny_humans.landmarks")

ANTERIOR = np.array([0.0, -1.0, 0.0])   # humans face -Y
AXIAL_CHAIN = ("root", "spine05", "spine04", "spine03", "spine02", "spine01", "neck01", "neck02", "neck03", "head")


def internal_offset_m(rule: dict, ap_depth: float, stature_m: float) -> float:
    if "fixed_cm" in rule:
        scale = stature_m / 1.70 if rule.get("scale_with_stature") else 1.0
        return float(rule["fixed_cm"]) / 100.0 * scale
    return ap_depth * float(rule["fraction"])


def spine_points(coords, body_indices, cfg: dict, anchors: dict, bvh: MeshBVH) -> dict:
    spine = cfg["spine"]
    top, bottom = coords[anchors[spine["top_anchor"]]], coords[anchors[spine["bottom_anchor"]]]
    body = coords[body_indices]
    midline = [tuple(p) for p in body[np.abs(body[:, 0]) < 0.006]]
    chain = [tuple(top), tuple(bottom)] + [tuple(coords[anchors[a]]) for a in spine["pins"].values()]
    profile = lm.posterior_profile(midline, chain, max_forward_m=float(spine.get("max_forward_cm", 4.0)) / 100.0)
    pins = {level: lm.project_to_arc(profile, tuple(coords[anchors[a]])) for level, a in spine["pins"].items()}
    s_top = lm.project_to_arc(profile, tuple(top)) + float(spine.get("top_offset_cm", 0.0)) / 100.0
    arc = lm.distribute_levels(spine["levels"], spine["segment_ratios"], pins,
                               s_top, lm.project_to_arc(profile, tuple(bottom)))
    stature = float(body[:, 2].max() - body[:, 2].min())
    surfaces = [np.array(lm.point_at_arc(profile, arc[level])) for level in spine["levels"]]
    hits = bvh.ray_cast_many([s + ANTERIOR * 0.002 for s in surfaces], [ANTERIOR] * len(surfaces), 1.0)
    emit = set(spine.get("emit", ["internal", "surface"]))
    points, centres = {}, []
    for level, surface, hit in zip(spine["levels"], surfaces, hits):
        depth = (hit[3] + 0.002) if hit[0] is not None else 0.12
        offset = internal_offset_m(spine["internal_depth"][lm.region_of(level)], depth, stature)
        if "surface" in emit:
            points[f"{level}_surf"] = {"position": surface, "kind": "surface", "level": level}
        centres.append(surface + ANTERIOR * offset)
        if "internal" in emit:
            points[level] = {"position": centres[-1], "kind": "internal", "level": level,
                             "ap_depth_m": round(depth, 4), "internal_offset_m": round(offset, 4)}
    for level, axes in zip(spine["levels"], landmark_rules.spine_axes(centres)):
        if level in points:
            points[level]["axes"] = axes
    return points


def apply_spine_shape(points: dict, levels: list, cfg: dict, subject: dict) -> dict:
    """Reshape the vertebral bodies to the patient's sampled kyphosis / lordosis / scoliosis."""
    centres = [np.asarray(points[lv]["position"]) for lv in levels]
    before = anatomy_rules.spine_curvature(centres, levels)
    rng = np.random.default_rng(int(subject.get("seed", 0)) + 7919)
    shape = anatomy_rules.sample_spine_shape(rng, float(subject.get("age", 40)), cfg)
    new, axial = anatomy_rules.reshape_spine(centres, levels, shape)
    for level, c, axes, deg in zip(levels, new, landmark_rules.spine_axes(new), axial):
        a = np.radians(deg)
        rot_y = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
        points[level]["position"] = np.asarray(c)
        points[level]["axes"] = axes @ rot_y
    return {"target": shape, "before": before, "after": anatomy_rules.spine_curvature(new, levels)}


def compute_landmarks(coords, body_indices, body_tris, cfg: dict, subject: dict = None) -> tuple:
    """-> (points, spine shape) for anchors, spine levels, frames and derived joints (USD space)."""
    anchors = cfg["anchors"]
    missing = [k for k, v in anchors.items() if v is None]
    if missing:
        raise ValueError(f"landmark anchors not calibrated: {missing}")
    bvh = MeshBVH(coords, body_tris)
    points = {name: {"position": coords[idx].copy(), "kind": "anchor", "vertex": int(idx)}
              for name, idx in anchors.items()}
    points.update(spine_points(coords, body_indices, cfg, anchors, bvh))
    shape = None
    if (cfg.get("spine_shape") or {}).get("enabled"):
        shape = apply_spine_shape(points, cfg["spine"]["levels"], cfg["spine_shape"], subject or {})
    wanted = lm.expand_parent_map((cfg.get("frames") or {}).get("parents", {}), [])
    rest = {name: np.asarray(info["position"]) for name, info in points.items()}
    for name, (origin, axes) in landmark_rules.anatomical_frames(rest).items():
        if anatomy_rules.parent_lookup(name, wanted):
            points[f"frame:{name}"] = {"position": np.asarray(origin), "kind": "frame", "frame": name, "axes": axes}
    skin = coords[body_indices]
    stature = float(skin[:, 2].max() - skin[:, 2].min())
    for name, info in anatomy_rules.derived_joints(rest, skin, stature).items():
        info = dict(info, position=np.asarray(info["position"]))
        if info["kind"] == "frame":
            if anatomy_rules.parent_lookup(info["frame"], wanted):
                points[f"frame:{info['frame']}"] = info
        else:
            points[name] = info
    return points, shape


def _segment_distance(p, a, b) -> float:
    ab = b - a
    t = np.clip((p - a) @ ab / max(ab @ ab, 1e-12), 0.0, 1.0)
    return float(np.linalg.norm(p - (a + ab * t)))


def _nearest_axial(point, index: dict, heads, tails) -> str:
    """Axial-chain bone whose head->tail segment is closest to the point."""
    chain = [n for n in AXIAL_CHAIN if n in index]
    return min(chain, key=lambda n: _segment_distance(point, heads[index[n]], tails[index[n]]))


def _parent_for(name: str, parents: dict, info: dict) -> str:
    return anatomy_rules.parent_lookup(name, parents) or parents.get(info.get("level", "")) or "root"


def to_joints(points: dict, cfg: dict, bone_labels, heads, tails):
    """-> (names, parent indices into bone_labels + new joints, world matrices [N, 4, 4], metadata).

    Joint frames are axis-aligned except vertebral bodies and anatomical frames, whose columns are
    X anterior, Y superior, Z subject right."""
    parents_cfg = lm.expand_parent_map(cfg["parent_bones"], cfg["spine"]["levels"])
    frames = cfg.get("frames") or {}
    frame_parents = lm.expand_parent_map(frames.get("parents", {}), [])
    prefix, frame_prefix = cfg.get("bone_prefix", "LM_"), frames.get("prefix", "AN_")
    index = {n: i for i, n in enumerate(bone_labels)}
    names, parents, world, meta = [], [], [], {}
    for name, info in points.items():
        if info["kind"] == "frame":
            joint = f"{frame_prefix}{info['frame']}"
            parent = anatomy_rules.parent_lookup(info["frame"], frame_parents, "root")
        else:
            joint, parent = f"{prefix}{name}", _parent_for(name, parents_cfg, info)
        if parent == "auto_axial":
            parent = _nearest_axial(info["position"], index, heads, tails)
        if parent not in index:
            _LOG.warning(f"parent bone {parent} missing for {name}; using root")
            parent = "root"
        m = np.eye(4)
        m[:3, 3] = info["position"]
        if info.get("axes") is not None:
            m[:3, :3] = np.asarray(info["axes"])
        names.append(joint)
        parents.append(index[parent])
        world.append(m)
        meta[name] = {**{k: v for k, v in info.items() if k not in ("position", "axes")},
                      "bone": joint, "parent": parent,
                      "rest_position_m": [round(float(c), 5) for c in info["position"]]}
        if info.get("axes") is not None:
            meta[name]["axes_xyz"] = np.round(np.asarray(info["axes"]).T, 5).tolist()
    _LOG.info(f"{len(names)} landmark / frame joints")
    return names, parents, np.array(world), meta
