"""IES profile of a rectangular collimator field (copy of room/sdg_room/usd/fov_light.py:write_rect_ies, used by
sdg only for rooms built before the room pipeline added Collimator/FOVLight). No third-party imports."""

import math


def write_rect_ies(path, half_w_deg, half_h_deg, candela=1000.0, edge_deg=0.4, v_step=0.25, h_step=2.5) -> None:
    """IES LM-63 (type C) profile: candela inside |tan(theta) cos(phi)| <= tan(half_w), |tan(theta) sin(phi)| <=
    tan(half_h) around the light's axis (phi = 0 along the light's +X), linear soft edge, 0 outside."""
    ta, tb = math.tan(math.radians(half_w_deg)), math.tan(math.radians(half_h_deg))
    vmax = math.degrees(math.atan(math.hypot(ta, tb))) + 3.0
    vs = [round(i * v_step, 4) for i in range(int(vmax / v_step) + 2)] + [90.0]
    hs = [round(i * h_step, 4) for i in range(int(360 / h_step) + 1)]
    soft = math.radians(edge_deg)
    lines = ["IESNA:LM-63-2002", "[TEST] sdg_room collimator field light", "TILT=NONE",
             f"1 -1 1 {len(vs)} {len(hs)} 1 2 0.02 0.02 0", "1 1 0",
             " ".join(f"{v:g}" for v in vs), " ".join(f"{h:g}" for h in hs)]
    for h in hs:
        row = []
        for v in vs:
            t = math.tan(math.radians(min(v, 89.9)))
            x, y = abs(t * math.cos(math.radians(h))), abs(t * math.sin(math.radians(h)))
            fx = min(1.0, max(0.0, (ta - x) / soft + 0.5))
            fy = min(1.0, max(0.0, (tb - y) / soft + 0.5))
            row.append(f"{candela * fx * fy:.2f}")
        lines.append(" ".join(row))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
