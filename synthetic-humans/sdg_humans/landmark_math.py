"""Pure-Python landmark maths (stdlib only; used inside Blender and in unit tests).

Points are plain (x, y, z) tuples so everything here is testable without bpy.
"""

import math
import re


# --- polyline helpers ---------------------------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def cumulative_lengths(polyline: list) -> list:
    lengths = [0.0]
    for a, b in zip(polyline, polyline[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    return lengths


def project_to_arc(polyline: list, point) -> float:
    """Arc length of the polyline point closest to `point`."""
    lengths = cumulative_lengths(polyline)
    best_s, best_d = 0.0, float("inf")
    for i, (a, b) in enumerate(zip(polyline, polyline[1:])):
        ab = _sub(b, a)
        denom = _dot(ab, ab) or 1e-12
        t = max(0.0, min(1.0, _dot(_sub(point, a), ab) / denom))
        d = math.dist(point, _lerp(a, b, t))
        if d < best_d:
            best_d, best_s = d, lengths[i] + t * math.dist(a, b)
    return best_s


def point_at_arc(polyline: list, s: float):
    lengths = cumulative_lengths(polyline)
    s = max(0.0, min(lengths[-1], s))
    for i in range(len(polyline) - 1):
        if lengths[i + 1] >= s:
            seg = lengths[i + 1] - lengths[i] or 1e-12
            return _lerp(polyline[i], polyline[i + 1], (s - lengths[i]) / seg)
    return polyline[-1]


# --- vertebra distribution ----------------------------------------------------------------

def distribute_levels(levels: list, ratios: dict, pins: dict, s_top: float, s_bottom: float) -> dict:
    """Arc position of every vertebra centre.

    `pins` maps level -> arc position of that level's centre (anchored on the body).
    `s_top` / `s_bottom` are the boundaries above the first and below the last level.
    Between two known points the free levels are placed proportionally to their segment
    ratios; a pinned level contributes half its ratio on each side of its centre.
    """
    known = [(-1, s_top, False)]
    known += sorted(((levels.index(lv), s, True) for lv, s in pins.items()), key=lambda k: k[0])
    known += [(len(levels), s_bottom, False)]
    result = {levels[i]: s for i, s, _ in known if 0 <= i < len(levels)}
    for (ia, sa, a_is_level), (ib, sb, b_is_level) in zip(known, known[1:]):
        between = list(range(ia + 1, ib))
        half_a = ratios[levels[ia]] / 2.0 if a_is_level else 0.0
        half_b = ratios[levels[ib]] / 2.0 if b_is_level else 0.0
        total = half_a + sum(ratios[levels[i]] for i in between) + half_b
        acc = half_a
        for i in between:
            r = ratios[levels[i]]
            result[levels[i]] = sa + (sb - sa) * (acc + r / 2.0) / total
            acc += r
    return result


def _interp_y(chain: list, z: float) -> float:
    """y of the anchor chain (sorted by descending z) at height z, linearly interpolated."""
    if z >= chain[0][2]:
        return chain[0][1]
    for a, b in zip(chain, chain[1:]):
        if b[2] <= z <= a[2]:
            t = (a[2] - z) / ((a[2] - b[2]) or 1e-9)
            return a[1] + (b[1] - a[1]) * t
    return chain[-1][1]


def posterior_profile(points: list, anchor_chain: list, bin_m: float = 0.01, max_forward_m: float = 0.04) -> list:
    """Posterior midline profile between the first and last anchor of `anchor_chain`.

    Per z bin the point with the largest y (back = +Y) is taken, but only points no more
    than `max_forward_m` in front of the anchor chain (spinous processes on the back) are
    considered, so throat, chin or belly vertices can never be mistaken for the back.
    """
    chain = sorted(anchor_chain, key=lambda p: -p[2])
    z_top, z_bottom = chain[0][2], chain[-1][2]
    bins = {}
    for p in points:
        if not (z_bottom < p[2] < z_top) or p[1] < _interp_y(chain, p[2]) - max_forward_m:
            continue
        key = int(math.floor(p[2] / bin_m))
        if key not in bins or p[1] > bins[key][1]:
            bins[key] = p
    return [chain[0]] + [bins[k] for k in sorted(bins, reverse=True)] + [chain[-1]]


# --- naming rules ---------------------------------------------------------------------------

def _expand_range(key: str, levels: list) -> list:
    m = re.match(r"^([A-Z])(\d+)-([A-Z])(\d+)$", key)
    if not m:
        return [key]
    start, end = f"{m.group(1)}{m.group(2)}", f"{m.group(3)}{m.group(4)}"
    if start not in levels or end not in levels:
        return [key]
    return levels[levels.index(start): levels.index(end) + 1]


def expand_parent_map(parent_bones: dict, levels: list) -> dict:
    """{'T1-T4': 'spine05', 'tragus_{side}': 'head'} -> {'T1': 'spine05', ..., 'tragus_L': 'head', ...}."""
    result = {}
    for key, bone in parent_bones.items():
        for name in _expand_range(key, levels):
            if "{side}" in name:
                for side in ("L", "R"):
                    result[name.replace("{side}", side)] = str(bone).replace("{side}", side)
            else:
                result[name] = str(bone).replace("{side}", "")
    return result


def region_of(level: str) -> str:
    return level[0]
