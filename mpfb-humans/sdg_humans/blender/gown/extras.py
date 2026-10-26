"""Gown extras: bow ties across the open back."""

TRIM_V = (0.93, 0.98)


def _box(b, centre, size) -> None:
    cx, cy, cz = centre
    hx, hy, hz = (s / 2 for s in size)
    corners = [b.add_vertex((cx + sx * hx, cy + sy * hy, cz + sz * hz), "body")
               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    c = lambda sx, sy, sz: corners[((sx > 0) << 2) | ((sy > 0) << 1) | (sz > 0)]  # noqa: E731
    faces = [((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)), ((1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)),
             ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)), ((-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)),
             ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1))]
    uvs = [(0.1, TRIM_V[0]), (0.2, TRIM_V[0]), (0.2, TRIM_V[1]), (0.1, TRIM_V[1])]
    for face in faces:
        b.add_quad([c(*corner) for corner in face], uvs)


def build_ties(b, info, variant, cfg) -> None:
    """Small bow knots (+ one hanging tail) across the open back at the configured heights."""
    if not variant.get("back_opening"):
        return
    n, rings, z_levels, cy = info["n"], info["rings"], info["z_levels"], info["centre"][1]
    width = float(cfg.get("back_opening_width_cm", 4.0)) / 100.0 + 0.03
    for fraction in cfg.get("tie_heights", [0.02, 0.4]):
        z = info["top_z"] - fraction * (info["top_z"] - info["hip_z"])
        zi = min(range(len(z_levels)), key=lambda k: abs(z_levels[k] - z))
        y = cy + rings[zi][n // 2] + 0.012
        _box(b, (0.0, y, z), (width, 0.004, 0.012))
        _box(b, (0.008, y + 0.003, z - 0.035), (0.008, 0.003, 0.06))
