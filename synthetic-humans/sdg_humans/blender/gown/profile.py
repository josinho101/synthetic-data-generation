"""Polar body profile of the neutral basemesh and the 'drape' rule of a loose gown.

r[z][θ] = largest distance from the vertical body axis of any torso / leg vertex in the
z band and angular bin (arms, hands, neck and head excluded). θ is measured from the front
(−Y) towards the left (+X): direction(θ) = (sin θ, −cos θ).
"""

import math

TORSO = {"root", "spine01", "spine02", "spine03", "spine04", "spine05", "breast.L", "breast.R",
         "pelvis.L", "pelvis.R", "clavicle.L", "clavicle.R", "shoulder01.L", "shoulder01.R"}
LEG_PREFIXES = ("upperleg", "lowerleg")


def direction(theta: float) -> tuple:
    return math.sin(theta), -math.cos(theta)


SHOULDER = {"clavicle.L", "clavicle.R", "shoulder01.L", "shoulder01.R"}


def is_profile_bone(name, include_shoulders: bool = True) -> bool:
    if not name or (not include_shoulders and name in SHOULDER):
        return False
    return name in TORSO or name.startswith(LEG_PREFIXES)


def polar_grid(coords, indices, centre, z_levels, n_theta, dz) -> list:
    """r[zi][ti] (0.0 where no vertex fell into the bin; filled afterwards)."""
    z0 = z_levels[0]
    grid = [[0.0] * n_theta for _ in z_levels]
    for i in indices:
        c = coords[i]
        zi = int(round((c.z - z0) / dz))
        if not 0 <= zi < len(z_levels):
            continue
        dx, dy = c.x - centre[0], c.y - centre[1]
        theta = math.atan2(dx, -dy) % (2 * math.pi)
        ti = int(theta / (2 * math.pi) * n_theta) % n_theta
        grid[zi][ti] = max(grid[zi][ti], math.hypot(dx, dy))
    return [_fill_ring(ring) for ring in grid]


def _fill_ring(ring: list) -> list:
    n = len(ring)
    known = [i for i, r in enumerate(ring) if r > 0]
    if not known:
        return ring
    out = list(ring)
    for i in range(n):
        if out[i] > 0:
            continue
        prev = max((k for k in known if k < i), default=known[-1] - n)
        nxt = min((k for k in known if k > i), default=known[0] + n)
        t = (i - prev) / (nxt - prev)
        out[i] = ring[prev % n] * (1 - t) + ring[nxt % n] * t
    return out


def smooth(grid: list, passes: int = 2) -> list:
    for _ in range(passes):
        n = len(grid[0])
        grid = [[(ring[(t - 1) % n] + 2 * ring[t] + ring[(t + 1) % n]) / 4 for t in range(n)] for ring in grid]
        grid = [[(grid[max(z - 1, 0)][t] + 2 * grid[z][t] + grid[min(z + 1, len(grid) - 1)][t]) / 4
                 for t in range(n)] for z in range(len(grid))]
    return grid


def drape(grid: list, z_levels: list, z_armpit: float, looseness: float, flare_per_m: float) -> list:
    """Above the armpit the gown follows the body; below it the fabric falls: each ring is at
    least as wide as the ring above it (cumulative maximum), plus an A-line flare."""
    out = [None] * len(grid)
    falling = None
    for zi in range(len(grid) - 1, -1, -1):
        ring = grid[zi]
        z = z_levels[zi]
        if z >= z_armpit:
            out[zi] = [r + looseness for r in ring]
            continue
        falling = list(ring) if falling is None else [max(a, b) for a, b in zip(falling, ring)]
        out[zi] = [r + looseness + flare_per_m * (z_armpit - z) for r in falling]
    return out
