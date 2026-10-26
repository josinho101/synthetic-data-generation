"""Gown body = draped lower tube (hem -> just below the armpits) + upper shell (shell.py).

UV layout (shared by all parts): u runs around the body (vertical stripes repeat along u,
seam at the back), v < 0.9 is fabric, 0.92-0.98 is the white trim band of the pattern.
"""

import math

from . import profile, shell

FABRIC_V = 0.88
TRIM_V = (0.93, 0.98)


def _u(x, y, centre, tiles) -> float:
    theta = math.atan2(x - centre[0], -(y - centre[1])) % (2 * math.pi)
    return tiles * ((theta / (2 * math.pi) + 0.5) % 1.0)      # seam at the back (theta = pi)


def _fix_wrap(us, tiles):
    if max(us) - min(us) > tiles / 2:
        return [u + tiles if u < tiles / 2 else u for u in us]
    return us


def _skip_back(points, centre_y, half_width, below_z=None) -> bool:
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    cz = sum(p[2] for p in points) / len(points)
    return half_width > 0 and abs(cx) < half_width and cy > centre_y and (below_z is None or cz < below_z)


def build_body(b, ctx, variant, cfg) -> dict:
    j, coords = ctx["joints"], ctx["coords"]
    n = int(cfg.get("segments_around", 64))
    dz = float(cfg.get("ring_spacing_cm", 1.5)) / 100.0
    hip_z = (j["l_upper_leg"].z + j["r_upper_leg"].z) / 2
    knee_z = (j["l_knee"].z + j["r_knee"].z) / 2
    shoulder_z = (j["l_shoulder"].z + j["r_shoulder"].z) / 2
    armpit_z = shoulder_z - float(cfg.get("armpit_drop_cm", 7.0)) / 100.0
    hem_z = hip_z + (knee_z - hip_z) * float(cfg["lengths"][variant["length"]])
    top_z = armpit_z - float(cfg.get("tube_top_below_armpit_cm", 3.0)) / 100.0
    seam_z = armpit_z - float(cfg.get("seam_below_armpit_cm", 12.0)) / 100.0
    steps = max(2, int(math.ceil((top_z - hem_z) / dz)))
    z_levels = [hem_z + (top_z - hem_z) * k / steps for k in range(steps + 1)]
    centre = (0.0, j["pelvis"].y)
    tiles = float(cfg.get("stripe_repeats_around", 16))
    half_open = float(cfg.get("back_opening_width_cm", 4.0)) / 200.0 if variant.get("back_opening") else 0.0

    # lower part: drape
    profile_idx = [i for i in ctx["body"] if profile.is_profile_bone(ctx["dom"].get(i), include_shoulders=False)]
    grid = profile.smooth(profile.polar_grid(coords, profile_idx, centre, z_levels, n, dz), 2)
    rings = profile.smooth(profile.drape(grid, z_levels, top_z + 1e-6, float(variant["looseness_cm"]) / 100.0,
                                         float(cfg.get("flare_cm_per_m", 6.0)) / 100.0), 1)
    ids = []
    for zi, z in enumerate(z_levels):
        group = "helper-skirt" if z < hip_z - 0.03 else "body"
        row = []
        for ti in range(n):
            dx, dy = profile.direction(2 * math.pi * ti / n)
            row.append(b.add_vertex((centre[0] + dx * rings[zi][ti], centre[1] + dy * rings[zi][ti], z), group))
        ids.append(row)
    for zi in range(steps):
        for ti in range(n):
            quad = [ids[zi][ti], ids[zi][(ti + 1) % n], ids[zi + 1][(ti + 1) % n], ids[zi + 1][ti]]
            pts = [b.verts[q] for q in quad]
            if _skip_back(pts, centre[1], half_open):
                continue
            us = _fix_wrap([_u(p[0], p[1], centre, tiles) for p in pts], tiles)
            vs = [FABRIC_V * zi / steps] * 2 + [FABRIC_V * (zi + 1) / steps] * 2
            b.add_quad(quad, list(zip(us, vs)))

    info = {"centre": centre, "z_levels": z_levels, "rings": rings, "n": n, "armpit_z": armpit_z,
            "hip_z": hip_z, "hem_z": hem_z, "top_z": shoulder_z + 0.05}

    # upper part: body-face shell (shoulders, neckline, sleeves) covering the drape top
    bm, sleeve, sleeve_end = shell.cut(ctx, variant, cfg, seam_z)
    shell.shape(bm, sleeve, sleeve_end, info, variant, cfg)
    trim_from = sleeve_end - float(cfg.get("sleeve_trim_fraction", 0.12))
    index = {}
    for v in bm.verts:
        index[v] = b.add_vertex(tuple(v.co), "body")
    span = max(info["top_z"] - hem_z, 1e-6)
    for f in bm.faces:
        verts = list(f.verts)
        if len(verts) != 4:
            continue
        pts = [tuple(v.co) for v in verts]
        if _skip_back(pts, centre[1], half_open, below_z=armpit_z):
            continue
        us = _fix_wrap([_u(p[0], p[1], centre, tiles) for p in pts], tiles)
        if all(sleeve[v] is not None and sleeve[v] >= trim_from for v in verts):
            vs = [TRIM_V[0], TRIM_V[0], TRIM_V[1], TRIM_V[1]]
        else:
            vs = [min(FABRIC_V, FABRIC_V * (p[2] - hem_z) / span) for p in pts]
        b.add_quad([index[v] for v in verts], list(zip(us, vs)))
    bm.free()
    return info
