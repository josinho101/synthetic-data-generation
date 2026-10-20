"""Photometry: target illuminance (lux) -> luminance (nits) of the ceiling RectLights.

Direct illuminance at a floor point p from a Lambertian rectangular emitter of luminance L facing down:

    E(p) = L * sum_over_patches( cos(theta_e) * cos(theta_r) / d^2 * dA )

The panel is split into small patches (numerical integration, exact in the limit). The light that bounces
off walls / ceiling is approximated by `indirect_gain`; `lux_calibration` corrects the remaining difference
to the renderer (measured once in Isaac Sim). UsdLux RectLight (normalize = false): emitted luminance in nits
= intensity * 2^exposure, so the solved L is written as `intensity` with exposure 0.
"""

import numpy as np


def unit_illuminance(points: np.ndarray, panels: list, height: float, subdiv: int = 8) -> np.ndarray:
    """Direct illuminance (lux) at `points` (N x 2, on the work plane z = 0) per 1 nit of panel luminance.

    `panels`: [{"center": [x, y], "size_m": [sx, sy]}], emitting downwards from z = `height` above the plane.
    """
    total = np.zeros(len(points))
    for panel in panels:
        (cx, cy), (sx, sy) = panel["center"], panel["size_m"]
        u = (np.arange(subdiv) + 0.5) / subdiv - 0.5
        px, py = np.meshgrid(cx + u * sx, cy + u * sy, indexing="ij")
        patch_area = sx * sy / subdiv ** 2
        dx = px.reshape(1, -1) - points[:, 0:1]
        dy = py.reshape(1, -1) - points[:, 1:2]
        d2 = dx * dx + dy * dy + height * height
        cos2 = (height * height) / d2              # cos(theta_e) * cos(theta_r) for parallel planes
        total += (cos2 / d2).sum(axis=1) * patch_area
    return total


def floor_grid(region, grid_m: float, exclude=None) -> np.ndarray:
    """Grid points (cell centres) inside region [x0, y0, x1, y1], optionally minus an excluded rect."""
    x0, y0, x1, y1 = region
    xs = np.arange(x0 + grid_m / 2, x1, grid_m)
    ys = np.arange(y0 + grid_m / 2, y1, grid_m)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    pts = np.stack([X.ravel(), Y.ravel()], axis=1)
    if exclude is not None:
        ex0, ey0, ex1, ey1 = exclude
        keep = ~((pts[:, 0] >= ex0) & (pts[:, 0] <= ex1) & (pts[:, 1] >= ey0) & (pts[:, 1] <= ey1))
        pts = pts[keep]
    return pts


def solve_luminance(target_lux: float, points, panels, height, indirect_gain=1.0, calibration=1.0) -> dict:
    """Panel luminance giving mean illuminance = target over `points`, plus the achieved statistics."""
    unit = unit_illuminance(points, panels, height)
    mean_unit = float(unit.mean())
    luminance = target_lux / (mean_unit * indirect_gain * calibration)
    direct = unit * luminance
    total = direct * indirect_gain
    return {"luminance_nits": luminance, "target_lux": target_lux,
            "direct_lux_mean": float(direct.mean()), "direct_lux_min": float(direct.min()),
            "direct_lux_max": float(direct.max()), "estimated_lux_mean": float(total.mean()),
            "estimated_lux_min": float(total.min()), "estimated_lux_max": float(total.max()),
            "uniformity_min_over_mean": float(direct.min() / direct.mean()),
            "indirect_gain": indirect_gain, "lux_calibration": calibration, "grid_points": int(len(points))}


def room_lighting(spec: dict, cfg: dict) -> dict:
    """Luminance of the exam-room panels and of the changing-room panel for one room."""
    light = cfg["lighting"]
    lay = spec["layout"]
    L, W = spec["footprint_m"]
    height = spec["ceiling_height_m"] - light.get("workplane_height_m", 0.0)
    exam_panels = [p for p in lay["panels"] if p["zone"] == "exam"]
    changing = [p for p in lay["panels"] if p["zone"] == "changing"]
    block = lay["changing_room"]["block"]
    exam_pts = floor_grid([0, 0, L, W], light["grid_m"], exclude=block)
    exam = solve_luminance(spec["lux_target"], exam_pts, exam_panels, height,
                           light["indirect_gain"], light["lux_calibration"])
    ch_pts = floor_grid(lay["changing_room"]["interior"], min(light["grid_m"], 0.1))
    ch = solve_luminance(spec["changing_lux_target"], ch_pts, changing, height,
                         light["indirect_gain"], light["lux_calibration"])
    return {"exam": exam, "changing": ch, "cct_k": spec["cct_k"], "cct_class": spec["cct_class"]}
