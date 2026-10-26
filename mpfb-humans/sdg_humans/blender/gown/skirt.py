"""Knee-length office (pencil) skirt: one tube from the natural waist to the knee.

From the waist down to the widest point of the hips the skirt follows the body (plus
looseness); below it the fabric falls straight (cumulative maximum of the body profile), so it
covers both legs like a pencil skirt. An optional taper narrows it slightly towards the hem.
UVs as for the gown (u around the body, seam at the back), so the same fabric texture tiles.
"""

import math

from . import profile
from .body_parts import FABRIC_V, _fix_wrap, _u


def build_skirt(b, ctx, variant, cfg) -> dict:
    j, coords = ctx["joints"], ctx["coords"]
    n = int(cfg.get("segments_around", 64))
    dz = float(cfg.get("ring_spacing_cm", 1.5)) / 100.0
    hip_z = (j["l_upper_leg"].z + j["r_upper_leg"].z) / 2
    knee_z = (j["l_knee"].z + j["r_knee"].z) / 2
    waist_z = hip_z + float(variant.get("waist_above_hip_cm", 10.0)) / 100.0
    hem_z = hip_z + (knee_z - hip_z) * float(cfg["lengths"][variant["length"]])
    steps = max(2, int(math.ceil((waist_z - hem_z) / dz)))
    z_levels = [hem_z + (waist_z - hem_z) * k / steps for k in range(steps + 1)]
    centre = (0.0, j["pelvis"].y)
    tiles = float(cfg.get("stripe_repeats_around", 16))

    idx = [i for i in ctx["body"] if profile.is_profile_bone(ctx["dom"].get(i), include_shoulders=False)]
    grid = profile.smooth(profile.polar_grid(coords, idx, centre, z_levels, n, dz), 2)
    taper = -float(variant.get("taper_cm_per_m", 0.0)) / 100.0
    rings = profile.smooth(profile.drape(grid, z_levels, waist_z + 1e-6, float(variant["looseness_cm"]) / 100.0,
                                         taper), 1)
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
            us = _fix_wrap([_u(p[0], p[1], centre, tiles) for p in pts], tiles)
            vs = [FABRIC_V * zi / steps] * 2 + [FABRIC_V * (zi + 1) / steps] * 2
            b.add_quad(quad, list(zip(us, vs)))
    return {"hem_z": hem_z, "top_z": waist_z}
