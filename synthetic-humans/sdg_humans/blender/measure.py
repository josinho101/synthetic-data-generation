"""Body measurements for the metadata: landmark heights, widths and depths (centimetres)."""

import logging

from . import geometry

_LOG = logging.getLogger("sdg_humans.blender.measure")


ARM_BONE_PREFIXES = ("upperarm", "lowerarm", "wrist", "finger", "metacarpal")


def _arm_vertices(basemesh, indices) -> set:
    """Vertices whose strongest rig weight belongs to an arm / hand bone."""
    arm_groups = {g.index for g in basemesh.vertex_groups if g.name.startswith(ARM_BONE_PREFIXES)}
    bone_groups = {g.index for g in basemesh.vertex_groups if "." in g.name or g.name.startswith(("spine", "neck"))}
    result = set()
    for i in indices:
        weights = [(g.weight, g.group) for g in basemesh.data.vertices[i].groups if g.group in bone_groups]
        if weights and max(weights)[1] in arm_groups:
            result.add(i)
    return result


def _slice(coords, indices, z, tol=0.015):
    return [i for i in indices if abs(coords[i].z - z) < tol]


def torso_width_cm(points) -> float:
    xs = [p.x for p in points]
    return round((max(xs) - min(xs)) * 100.0, 2) if xs else None


def ap_depth_cm(points, half_width=0.03) -> float:
    ys = [p.y for p in points if abs(p.x) < half_width]
    return round((max(ys) - min(ys)) * 100.0, 2) if ys else None


def measure(basemesh, landmarks: dict, cfg_landmarks: dict) -> dict:
    coords = geometry.evaluated_coords(basemesh)
    body = geometry.group_vertex_indices(basemesh, "body")
    lo, hi = geometry.body_extent(coords, body)
    out = {"stature_cm": round((hi - lo) * 100.0, 2)}
    for name, key in (cfg_landmarks.get("heights_from_landmarks") or {}).items():
        info = landmarks.get(name)
        if info:
            out[key] = round(info["rest_position_m"][2] * 100.0, 2)
    for label, landmark in (("chest", "xiphoid"), ("abdomen", "navel")):
        if landmark in landmarks:
            z = landmarks[landmark]["rest_position_m"][2]
            ring = _slice(coords, body, z)
            arms = _arm_vertices(basemesh, ring)
            torso = [coords[i] for i in ring if i not in arms]
            out[f"{label}_width_cm"] = torso_width_cm(torso)
            out[f"{label}_ap_depth_cm"] = ap_depth_cm(torso)
    if "acromion_L" in landmarks and "acromion_R" in landmarks:
        out["biacromial_width_cm"] = round(abs(landmarks["acromion_L"]["rest_position_m"][0]
                                               - landmarks["acromion_R"]["rest_position_m"][0]) * 100.0, 2)
    _LOG.info(f"measurements: {out}")
    return out
