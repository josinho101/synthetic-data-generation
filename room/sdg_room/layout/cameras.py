"""Camera poses (room frame) solved from a room layout: mounts, look-at targets, optics."""

import math

import numpy as np

from ..placement import entrance_outward
from ..sampling.distributions import uniform
from .coverage import GROUPS, best_view, in_frame, occluders, patient_points, unoccluded
from .geometry import Rect

FAR_WALL = {"west": "east", "east": "west", "south": "north", "north": "south"}


def _targets(spec: dict) -> dict:
    lay = spec["layout"]
    L, W = spec["footprint_m"]
    cr = lay["changing_room"]
    it = Rect.from_list(cr["interior"])
    ent = lay["entrance"]
    return {"room_center": [L / 2, W / 2, 0.8],
            "floor_marker": lay["marker"]["stand_point"] + [1.0],
            "detector": list(lay["equipment"]["detector"]["center"]),
            "checkin_center": [it.cx, it.cy, 0.7],
            "checkin_door": cr["door"]["center"] + [1.0],
            "entrance_door": ent["center"] + [1.0]}


def _far_wall_mounts(spec: dict, c: dict):
    """Both high corners of the wall opposite the entrance: ({'left': xyz, 'right': xyz}, wall name)."""
    lay = spec["layout"]
    L, W = spec["footprint_m"]
    H = spec["ceiling_height_m"]
    out = entrance_outward(spec)
    inward = (-out[0], -out[1])
    left = (-inward[1], inward[0])            # to the viewer's left when looking into the room
    far = FAR_WALL[lay["entrance"]["wall"]]
    block = Rect.from_list(lay["changing_room"]["block"])
    off, inset, z = c["wall_offset_m"], c["corner_inset_m"], H - c["ceiling_gap_m"]
    if far in ("east", "west"):
        x = L - off if far == "east" else off
        lo, hi = 0.0, W
        if far == "west":    # the changing room sits on the west wall
            lo, hi = (0.0, block.y0) if block.y1 >= W - 1e-6 else (block.y1, W)
        a, b = [x, lo + inset, z], [x, hi - inset, z]
    else:
        y = W - off if far == "north" else off
        on_wall = (block.y1 >= W - 1e-6) if far == "north" else (block.y0 <= 1e-6)
        lo = block.x1 if on_wall else 0.0
        a, b = [lo + inset, y, z], [L - inset, y, z]
    da, db = a[0] * left[0] + a[1] * left[1], b[0] * left[0] + b[1] * left[1]
    return ({"left": a, "right": b} if da > db else {"left": b, "right": a}), far


def _auto_frame(spec, cov, mounts, side, groups, boxes, ha, va, rng):
    """Search mount positions from this camera's corner towards the middle of the far wall; at each one aim the
    camera and choose the lens that frames the patient (and the room) best. Returns (eye, forward, focal, vis)."""
    end = np.array(mounts[side], float)
    other = np.array(mounts["right" if side == "left" else "left"], float)
    span = float(np.linalg.norm(other - end))
    step = float(cov["search_step_m"])
    reach = span * float(cov["search_fraction"])
    best = None
    k, offset = 0, rng.uniform(0.0, step * 0.5)
    while offset + k * step <= reach + 1e-9:
        eye = end + (other - end) * ((offset + k * step) / span if span > 0 else 0.0)
        s, fwd, focal, vis = best_view(eye, groups, boxes, ha, va, cov)
        if best is None or s > best[0] + 1e-6:
            best = (s, eye, fwd, focal, vis)
        k += 1
    return best[1:]


def _checkin_mount(spec: dict, c: dict):
    cr = spec["layout"]["changing_room"]
    it = Rect.from_list(cr["interior"])
    dx, dy = cr["door"]["center"]
    corners = [(it.x0, it.y0), (it.x1, it.y0), (it.x1, it.y1), (it.x0, it.y1)]
    cx, cy = max(corners, key=lambda p: (p[0] - dx) ** 2 + (p[1] - dy) ** 2)
    sx = 1 if cx == it.x0 else -1
    sy = 1 if cy == it.y0 else -1
    return [cx + sx * c["wall_offset_m"], cy + sy * c["corner_inset_m"], spec["ceiling_height_m"] - c["ceiling_gap_m"]]


def _entrance_mount(spec: dict, cfg: dict):
    p = cfg["export"].get("placement") or {}
    out = entrance_outward(spec)
    cx, cy = spec["layout"]["entrance"]["center"]
    d = float(p.get("viewer_distance_m", 6.0))
    return [cx + out[0] * d, cy + out[1] * d, float(p.get("viewer_height_m", 2.0))]


def fov_deg(aperture_mm, focal_mm) -> float:
    return math.degrees(2 * math.atan(aperture_mm / (2 * focal_mm)))


def solve_cameras(cfg: dict, spec: dict, rng):
    """Returns (cameras, coverage): camera poses + optics, and how much of the patient's actions the room
    cameras see together (fraction of sample points per group)."""
    ccfg = cfg.get("cameras") or {}
    if not ccfg.get("enabled", True):
        return [], {}
    targets = _targets(spec)
    defaults = ccfg.get("defaults") or {}
    cov = ccfg.get("coverage") or {}
    L, W = spec["footprint_m"]
    H = spec["ceiling_height_m"]
    room = Rect(0, 0, L, W)
    it = Rect.from_list(spec["layout"]["changing_room"]["interior"])
    groups = patient_points(spec, cfg) if cov else None
    boxes = occluders(spec, cfg) if cov else None
    out, room_vis = [], []
    for name, own in (ccfg.get("cameras") or {}).items():
        c = {**defaults, **(own or {})}
        if not c.get("enabled", True):
            continue
        mount = c["mount"]
        ha = float(c["horizontal_aperture_mm"])
        res = list(c["resolution"])
        va = ha * res[1] / res[0]
        auto = bool(c.get("auto_frame")) and mount in ("far_wall_left", "far_wall_right") and cov
        vis = None
        if auto:
            mounts, _ = _far_wall_mounts(spec, c)
            eye, fwd, focal, vis = _auto_frame(spec, cov, mounts, mount.rsplit("_", 1)[1], groups, boxes, ha, va, rng)
            pos, zone = [float(v) for v in eye], "room"
            target = [float(v) for v in eye + fwd * 3.0]
        else:
            if isinstance(mount, list):
                pos, zone = list(mount), "fixed"
            elif mount in ("far_wall_left", "far_wall_right"):
                mounts, _ = _far_wall_mounts(spec, c)
                pos, zone = list(mounts[mount.rsplit("_", 1)[1]]), "room"
            elif mount == "checkin_corner":
                pos, zone = _checkin_mount(spec, c), "checkin"
            elif mount == "entrance_outside":
                pos, zone = _entrance_mount(spec, cfg), "outside"
            else:
                raise ValueError(f"cameras.{name}.mount: unknown mount {mount!r}")
            target = list(c["target"]) if isinstance(c["target"], list) else list(targets[c["target"]])
            pj, tj = float(c.get("position_jitter_m", 0.0)), float(c.get("target_jitter_m", 0.0))
            pos = [pos[0] + rng.uniform(-pj, pj), pos[1] + rng.uniform(-pj, pj), pos[2] + rng.uniform(-pj, pj)]
            target = [target[0] + rng.uniform(-tj, tj), target[1] + rng.uniform(-tj, tj), target[2]]
            focal = round(uniform(rng, c["focal_length_mm"]), 3) if isinstance(c["focal_length_mm"], list) \
                else float(c["focal_length_mm"])
        box = room if zone == "room" else it if zone == "checkin" else None
        if box is not None:   # jitter never pushes a lens into a wall or the ceiling
            pos = [min(max(pos[0], box.x0 + 0.05), box.x1 - 0.05), min(max(pos[1], box.y0 + 0.05), box.y1 - 0.05),
                   min(pos[2], H - 0.08)]
        focal = round(float(focal), 3)
        if zone == "room" and groups is not None:
            if vis is None:
                eye = np.array(pos, float)
                vis = {g: in_frame(eye, np.array(target) - eye, groups[g], ha / (2 * focal), va / (2 * focal))
                       & unoccluded(eye, groups[g], boxes) for g in GROUPS}
            room_vis.append(vis)
        entry = {"name": name, "mount": mount if isinstance(mount, str) else "fixed", "zone": zone,
                 "auto_frame": bool(auto),
                 "position": [round(v, 4) for v in pos], "target": [round(v, 4) for v in target],
                 "target_name": "auto" if auto else (c["target"] if isinstance(c["target"], str) else "fixed"),
                 "focal_length_mm": focal, "horizontal_aperture_mm": ha, "vertical_aperture_mm": round(va, 4),
                 "fov_h_deg": round(fov_deg(ha, focal), 2), "fov_v_deg": round(fov_deg(va, focal), 2),
                 "resolution": res, "clipping_range_m": list(c["clipping_range_m"]),
                 "housing": bool(c.get("housing", False)) and zone in ("room", "checkin")}
        if vis is not None:
            entry["coverage"] = {g: round(float(v.mean()), 3) for g, v in vis.items() if len(v)}
        out.append(entry)
    coverage = {}
    if room_vis:
        for g in GROUPS:
            if len(groups[g]):
                union = np.zeros(len(groups[g]), dtype=bool)
                for v in room_vis:
                    union |= v[g]
                coverage[g] = round(float(union.mean()), 3)
        coverage["points"] = {g: int(len(groups[g])) for g in GROUPS}
    return out, coverage
