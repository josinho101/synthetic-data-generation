"""Body measurements for the metadata: landmark heights, widths and depths (centimetres)."""

import logging

import numpy as np

_LOG = logging.getLogger("anny_humans.measure")

ARM_BONE_PREFIXES = ("upperarm", "lowerarm", "wrist", "finger", "metacarpal")


def torso_width_cm(points) -> float:
    return round(float(np.ptp(points[:, 0])) * 100.0, 2) if len(points) else None


def ap_depth_cm(points, half_width=0.03) -> float:
    ys = points[np.abs(points[:, 0]) < half_width, 1]
    return round(float(np.ptp(ys)) * 100.0, 2) if len(ys) else None


def measure(body, coords, landmarks: dict, cfg_landmarks: dict) -> dict:
    """coords: all hm08 vertices of the fitted rest body (USD space)."""
    idx = body.body_vertices
    z = coords[idx, 2]
    out = {"stature_cm": round(float(z.max() - z.min()) * 100.0, 2)}
    for name, key in (cfg_landmarks.get("heights_from_landmarks") or {}).items():
        info = landmarks.get(name)
        if info:
            out[key] = round(info["rest_position_m"][2] * 100.0, 2)
    dominant = body.dominant_bones()
    arm_bones = {i for i, b in enumerate(body.bone_labels) if b.startswith(ARM_BONE_PREFIXES)}
    for label, landmark in (("chest", "xiphoid"), ("abdomen", "navel")):
        if landmark in landmarks:
            level = landmarks[landmark]["rest_position_m"][2]
            ring = idx[np.abs(coords[idx, 2] - level) < 0.015]
            torso = coords[[i for i in ring if int(dominant[i]) not in arm_bones]]
            out[f"{label}_width_cm"] = torso_width_cm(torso)
            out[f"{label}_ap_depth_cm"] = ap_depth_cm(torso)
    if "acromion_L" in landmarks and "acromion_R" in landmarks:
        out["biacromial_width_cm"] = round(abs(landmarks["acromion_L"]["rest_position_m"][0]
                                               - landmarks["acromion_R"]["rest_position_m"][0]) * 100.0, 2)
    _LOG.info(f"measurements: {out}")
    return out
