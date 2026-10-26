"""Axial skeleton: skull + mandible, vertebrae (C1-S5) + coccyx, ribs, sternum.

Positions come from the human's landmarks (rest pose, meters) and its body surface; all
sizes scale with stature (ctx["s"] = stature / 1.70 m). Front = -Y, left = +X.
"""

import math

from mathutils import Vector

from .prims import MeshAcc, ellipsoid, tube

POSTERIOR = Vector((0.0, 1.0, 0.0))
VERTEBRA_RADIUS_CM = {"C": 0.9, "T": 1.3, "L": 2.0, "S": 1.6}


def skull(ctx) -> dict:
    lm, s = ctx["lm"], ctx["s"]
    tl, tr, vertex, nasion, inion, chin = (lm[k] for k in ("tragus_L", "tragus_R", "vertex", "nasion", "inion", "chin"))
    centre = Vector((0.0, (nasion.y + inion.y) / 2, (tl.z + tr.z) / 2 + 0.03 * s))
    cranium = MeshAcc()
    ellipsoid(cranium, centre, ((tl.x - tr.x) / 2 * 0.92, (inion.y - nasion.y) / 2 * 0.9,
                                (vertex.z - centre.z) * 0.92), "head", rings=10, segments=16)
    # facial skeleton: its front stays 1 cm behind the nasion plane, clear of the nostril channels
    # (open holes in the skin mesh); the nose itself is cartilage
    ellipsoid(cranium, (0.0, nasion.y + 0.045 * s, (nasion.z + chin.z) / 2 + 0.01 * s),
              (0.045 * s, 0.035 * s, (nasion.z - chin.z) / 2 * 0.8), "head")
    mandible = MeshAcc()
    jaw = "jaw" if "jaw" in ctx["bones"] else "head"
    tmj = [Vector((p.x * 0.85, p.y - 0.005 * s, p.z - 0.012 * s)) for p in (tl, tr)]
    gonion = [Vector((p.x * 0.8, p.y + 0.005 * s, chin.z + 0.025 * s)) for p in tmj]
    menton = chin + Vector((0.0, 0.01 * s, 0.008 * s))
    tube(mandible, [tmj[0], gonion[0], menton.lerp(gonion[0], 0.5), menton, menton.lerp(gonion[1], 0.5),
                    gonion[1], tmj[1]], 0.007 * s, lambda t: {jaw: 1.0}, radius_y=0.012 * s, hint=Vector((0, 0, 1)))
    return {"skull": (cranium, "head"), "mandible": (mandible, jaw)}


def vertebrae(ctx) -> dict:
    lm, s, levels, parents = ctx["lm"], ctx["s"], ctx["levels"], ctx["lm_parent"]
    out = {}
    for k, level in enumerate(levels):
        centre = lm[level]
        prev_c = lm[levels[max(k - 1, 0)]]
        next_c = lm[levels[min(k + 1, len(levels) - 1)]]
        axis = (prev_c - next_c).normalized()
        spacing = (prev_c - next_c).length / (2 if 0 < k < len(levels) - 1 else 1)
        region = level[0]
        r = VERTEBRA_RADIUS_CM[region] / 100.0 * s
        bone = parents[level]
        acc = MeshAcc()
        half = axis * spacing * 0.35
        if region == "S":  # sacral segments: wide, flat, narrowing caudally
            width = (0.055 - 0.009 * int(level[1:])) * s
            ellipsoid(acc, centre, (width, 0.012 * s, spacing * 0.45), bone)
        else:
            tube(acc, [centre - half, centre + half], r, lambda t: {bone: 1.0}, segments=10, radius_y=r * 0.8)
            tip = lm[f"{level}_surf"] - POSTERIOR * 0.008 * s
            tube(acc, [centre + POSTERIOR * r * 0.8, tip], [0.004 * s, 0.0025 * s], lambda t: {bone: 1.0}, segments=6)
            for side in (-1, 1):
                lateral = Vector((side, 0.0, 0.0))
                tube(acc, [centre + lateral * r * 0.7 + POSTERIOR * r * 0.6,
                           centre + lateral * (r + 0.018 * s) + POSTERIOR * r * 1.1],
                     0.003 * s, lambda t: {bone: 1.0}, segments=6)
        out[f"vertebra_{level}"] = (acc, bone)
    coccyx = MeshAcc()
    tube(coccyx, [lm[levels[-1]], lm["coccyx"] - POSTERIOR * 0.012 * s], [0.008 * s, 0.003 * s],
         lambda t: {parents[levels[-1]]: 1.0}, segments=8)
    out["coccyx"] = (coccyx, parents[levels[-1]])
    return out


def _chest_point(ctx, origin: Vector, theta: float):
    """Point on the inner chest wall in direction theta (from front, towards +X) at origin.z."""
    direction = Vector((math.sin(theta), -math.cos(theta), 0.0))
    hit, _n, _i, distance = ctx["torso_bvh"].ray_cast(origin, direction, 1.0)
    if hit is None:
        return None
    inset = max(ctx["soft_tissue_m"], ctx["soft_tissue_fraction"] * distance)
    return origin + direction * (distance - inset)


def ribs(ctx) -> dict:
    lm, s, cfg = ctx["lm"], ctx["s"], ctx["cfg"]
    drops = cfg["rib_anterior_drop_cm"]
    ends = cfg["rib_end_angle_deg"]
    out = {}
    for i in range(1, 13):
        level = f"T{i}"
        bone = ctx["lm_parent"][level]
        spine_pt = lm[level]
        front_z = spine_pt.z - drops[i - 1] / 100.0 * s
        centre_y = (spine_pt.y + ctx["front_y_at"](spine_pt.z)) / 2
        for side, sign in (("L", 1), ("R", -1)):
            points = [spine_pt + Vector((sign * 0.012 * s, 0.006 * s, 0.0))]
            steps = 14
            end = math.radians(ends[i - 1])
            for k in range(steps + 1):
                f = k / steps
                theta = math.pi - 0.35 - (math.pi - 0.35 - end) * f
                z = spine_pt.z + (front_z - spine_pt.z) * (1 - math.cos(f * math.pi / 2))
                p = _chest_point(ctx, Vector((0.0, centre_y, z)), sign * theta)
                if p is not None:
                    points.append(p)
            if len(points) >= 4:
                acc = MeshAcc()
                tube(acc, points, 0.0045 * s, lambda t: {bone: 1.0}, segments=6, radius_y=0.0028 * s,
                     hint=Vector((0, 0, 1)))
                out[f"rib_{side}_{i:02d}"] = (acc, bone)
    return out


def sternum(ctx) -> dict:
    lm, s = ctx["lm"], ctx["s"]
    top, bottom = lm["jugular_notch"], lm["xiphoid"]
    pts = [top.lerp(bottom, f) for f in (0.0, 0.15, 0.3, 0.65, 1.0)]
    pts = [p + POSTERIOR * max(ctx["soft_tissue_m"], 0.012 * s) for p in pts]
    widths = [0.025 * s, 0.028 * s, 0.018 * s, 0.016 * s, 0.006 * s]
    acc = MeshAcc()
    bone = ctx["lm_parent"].get("xiphoid", "spine04")
    tube(acc, pts, widths, lambda t: {bone: 1.0}, segments=8, radius_y=0.005 * s, hint=Vector((1, 0, 0)))
    return {"sternum": (acc, bone)}
