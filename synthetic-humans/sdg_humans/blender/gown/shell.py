"""Upper gown shell cut from the neutral basemesh (shoulders, neckline, short sleeves).

Faces dominated by torso bones, plus upper-arm faces up to the sleeve end, from the
neckline down to a seam below the armpits. The shell is smoothed and offset from the skin;
below the armpits it is pushed out over the draped lower part, so the join reads as a yoke
seam instead of a fold.
"""

import math

import bmesh

from .. import geometry
from .profile import TORSO, direction

UPPER_ARM = ("upperarm01", "upperarm02")


def _arm_fraction(co, shoulder, elbow) -> float:
    axis = elbow - shoulder
    return (co - shoulder).dot(axis) / axis.length_squared


def cut(ctx, variant: dict, cfg: dict, seam_z: float):
    """bmesh of the upper shell + per-vertex sleeve fraction (None for torso vertices)."""
    j, coords, dom = ctx["joints"], ctx["coords"], ctx["dom"]
    neck = j["neck"]
    ring = [coords[i] for i in ctx["body"] if abs(coords[i].z - (neck.z + 0.03)) < 0.01]
    neck_r = max((math.hypot(c.x - neck.x, c.y - neck.y) for c in ring), default=0.06)
    drop_f = float(cfg.get("neckline_drop_front_cm", 4.0)) / 100.0
    drop_b = float(cfg.get("neckline_drop_back_cm", 2.0)) / 100.0
    sleeve_end = float(cfg["sleeve_ends"][variant["sleeve"]])
    body = set(ctx["body"])
    fraction = {}

    def keep(i, co):
        bone = dom.get(i) or ""
        if bone.startswith(UPPER_ARM):
            side = "l" if bone.endswith(".L") else "r"
            t = _arm_fraction(co, j[f"{side}_shoulder"], j[f"{side}_elbow"])
            if t > sleeve_end:
                return False
            fraction[i] = max(0.0, t)
        elif bone not in TORSO:
            return False
        horizontal = math.hypot(co.x - neck.x, co.y - neck.y)
        front = max(0.0, -(co.y - neck.y)) / max(horizontal, 1e-6)
        if horizontal < neck_r + 0.018 and co.z > neck.z - (drop_b + (drop_f - drop_b) * front):
            return False
        return co.z >= seam_z

    bm = bmesh.new()
    bm.from_mesh(ctx["basemesh"].data)
    geometry.strip_layers(bm)
    bm.verts.ensure_lookup_table()
    for v in bm.verts:
        v.co = coords[v.index]
    kept = {v.index for v in bm.verts if v.index in body and keep(v.index, v.co)}
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not all(v.index in kept for v in f.verts)], context="FACES_ONLY")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    sleeve = {v: fraction.get(v.index) for v in bm.verts}
    return bm, sleeve, sleeve_end


def shape(bm, sleeve: dict, sleeve_end: float, info: dict, variant: dict, cfg: dict) -> None:
    """Smooth, offset from the skin (wider towards the sleeve ends), cover the drape below the armpits."""
    interior = [v for v in bm.verts if not v.is_boundary]
    for _ in range(int(cfg.get("shell_smooth_iterations", 12))):
        bmesh.ops.smooth_vert(bm, verts=interior, factor=0.5, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    for _ in range(3):
        bmesh.ops.smooth_vert(bm, verts=[v for v in bm.verts if v.is_boundary], factor=0.5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.normal_update()
    loose = float(variant["looseness_cm"]) / 100.0
    widen = float(cfg.get("sleeve_widen_cm", 2.0)) / 100.0
    for v in bm.verts:
        t = sleeve[v]
        extra = widen * (t / sleeve_end) if t is not None and sleeve_end > 0 else 0.0
        v.co += v.normal * (loose + extra)
    centre, n, z_levels, rings = info["centre"], info["n"], info["z_levels"], info["rings"]
    cover = float(cfg.get("seam_cover_cm", 0.4)) / 100.0
    for v in bm.verts:
        if sleeve[v] is not None or v.co.z > info["armpit_z"]:
            continue
        dx, dy = v.co.x - centre[0], v.co.y - centre[1]
        theta = math.atan2(dx, -dy) % (2 * math.pi)
        zi = min(range(len(z_levels)), key=lambda k: abs(z_levels[k] - v.co.z))
        target = rings[zi][int(theta / (2 * math.pi) * n) % n] + cover
        r = math.hypot(dx, dy)
        if r < target:
            ux, uy = direction(theta)
            v.co.x, v.co.y = centre[0] + ux * target, centre[1] + uy * target
