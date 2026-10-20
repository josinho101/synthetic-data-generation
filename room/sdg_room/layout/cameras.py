"""Camera poses (room frame) solved from a room layout: mounts, look-at targets, optics."""

import math

import numpy as np

from ..placement import entrance_outward
from ..sampling.distributions import number, uniform
from .coverage import GROUPS, best_view, in_frame, occluders, patient_points, unoccluded
from .geometry import Rect
from .solver import LATERAL_MOUNTS, detector_axes, exam_cameras_cfg

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
    """Both high corners of the wall opposite the X-ray room's entry (the connecting door from the check-in room in
    the west wall): ({'left': xyz, 'right': xyz}, wall name). Left / right = seen from the entry looking in (+X)."""
    L, W = spec["footprint_m"]
    H = spec["ceiling_height_m"]
    off, inset, z = c["wall_offset_m"], c["corner_inset_m"], H - c["ceiling_gap_m"]
    x = L - off
    return {"left": [x, W - inset, z], "right": [x, inset, z]}, "east"


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


# --- exam cameras (RGB-D rigs, e.g. Intel RealSense D455) -----------------------------------------------------
EXAM_MOUNTS = LATERAL_MOUNTS + ("tube_head", "detector_top")
EXAM_TARGETS = ("patient_side", "patient_top")
STAND_TYPES = ("tripod", "bracket", "post_arm", "none")


def movement_zone(spec: dict, c: dict, rng) -> dict:
    """Sample points of the patient moving at the exam position (room frame).
    floor: the floor-marker outline grown by movement_margin_m (feet / top-down view);
    body:  feet-to-head columns at the marker centre and the corners of the marker outline (side views)."""
    lay = spec["layout"]
    marker = Rect.from_list(lay["marker"]["outline"])
    zone = marker.inflate(number(rng, c.get("movement_margin_m", 0.3)))
    top = number(rng, c.get("body_height_m", 1.85))
    floor = [[x, y, 0.02] for x in np.linspace(zone.x0, zone.x1, 5) for y in np.linspace(zone.y0, zone.y1, 4)]
    sx, sy = lay["marker"]["stand_point"]
    cols = [(sx, sy)] + [(x, y) for x in (marker.x0, marker.x1) for y in (marker.y0, marker.y1)]
    body = [[x, y, z] for x, y in cols for z in np.linspace(0.05, top, 6)]
    return {"floor": np.array(floor, float), "body": np.array(body, float), "zone": zone, "top": top}


def view_axes(forward, up):
    """Camera frame (forward, right, up) for a look direction and an approximate up vector."""
    f = np.asarray(forward, float)
    f = f / np.linalg.norm(f)
    r = np.cross(f, np.asarray(up, float))
    r = r / np.linalg.norm(r)
    return f, r, np.cross(r, f)


def frame_fraction(eye, forward, up, points, tan_h, tan_v) -> float:
    """Fraction of points inside the frustum of a camera with an explicit up vector (any orientation)."""
    if len(points) == 0:
        return 1.0
    f, r, u = view_axes(forward, up)
    d = points - np.asarray(eye, float)
    z = d @ f
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = (z > 0.05) & (np.abs((d @ r) / z) <= tan_h) & (np.abs((d @ u) / z) <= tan_v)
    return float(ok.mean())


def stream_optics(sensor: dict, stream: str, orientation: str = "landscape") -> dict:
    """USD optics of one sensor stream from its datasheet FOV (shared horizontal aperture, own focal length).
    portrait = the sensor mounted on its side with an upright camera: FOV h <-> v and resolution swapped (tall image),
    and the sensor offset turned with it (sensor right -> camera up)."""
    s = sensor[stream]
    ha = float(sensor.get("horizontal_aperture_mm", 20.955))
    fov, res = list(s["fov_deg"]), list(s["resolution"])
    ox, oy, oz = s.get("offset_m", [0.0, 0.0, 0.0])
    offset = [ox, oy, oz]
    if orientation == "portrait":
        fov, res, offset = fov[::-1], res[::-1], [-oy, ox, oz]
    fh, fv = (math.radians(v) for v in fov)
    focal = ha / (2 * math.tan(fh / 2))
    va = 2 * focal * math.tan(fv / 2)
    return {"focal_length_mm": round(focal, 4), "horizontal_aperture_mm": ha, "vertical_aperture_mm": round(va, 4),
            "fov_h_deg": float(fov[0]), "fov_v_deg": float(fov[1]), "resolution": res, "offset_m": offset,
            "range_m": list(s["range_m"]) if s.get("range_m") else None}


def _exam_target(spec, cfg, c, targets, zone):
    t = c.get("target")
    if isinstance(t, list):
        return [float(v) for v in t]
    if t == "patient_side":
        return [zone["zone"].cx, zone["zone"].cy, zone["top"] / 2]
    if t == "patient_top":
        return [zone["zone"].cx, zone["zone"].cy, 0.0]
    return list(targets[t])


def _exam_mount(spec, cfg, name, c, rng):
    """(eye, attached_to, mount_info) of an exam camera in the room frame."""
    lay, eq_cfg = spec["layout"], cfg["equipment"]
    eq = lay["equipment"]
    mount = c["mount"]
    if isinstance(mount, list):
        return [float(v) for v in mount], "floor", {}
    if mount in LATERAL_MOUNTS:
        stand = (lay.get("exam_cameras") or {}).get(name)
        if stand is None:
            raise ValueError(f"exam camera {name}: no tripod spot in the layout")
        return list(stand["position"]), "floor", {"stand_rect": stand["stand_rect"], "swing_deg": stand["swing_deg"]}
    if mount == "tube_head":
        ox, oy, oz = (number(rng, v) for v in c.get("offset_m", [0.0, 0.20, 0.16]))
        fx, fy, fz = eq["focal_spot"]
        a = math.radians(eq["tube_stand"]["yaw_deg"])
        eye = [fx + ox * math.cos(a) - oy * math.sin(a), fy + ox * math.sin(a) + oy * math.cos(a), fz + oz]
        t_cfg = eq_cfg["tube_stand"]                     # bracket foot: top of the collimator or of the housing
        base_z = fz + (t_cfg["collimator_size_m"][2] / 2 if oy > 0.6 * t_cfg["housing_radius_m"]
                       else t_cfg["housing_radius_m"])
        return eye, "tube_head", {"base_z": base_z}
    if mount == "detector_top":
        n, _ = detector_axes(eq)
        cx, cy, h = eq["detector"]["center"]
        hdp, hh = eq_cfg["detector"]["housing_size_m"][2], eq_cfg["detector"]["housing_size_m"][1]
        ext, rise = number(rng, c.get("extension_m", 0.2)), number(rng, c.get("rise_m", 0.1))
        top = h + hh / 2
        eye = [cx + n[0] * ext, cy + n[1] * ext, top + rise]
        post = [cx - n[0] * (hdp - 0.015), cy - n[1] * (hdp - 0.015)]     # back edge of the housing top
        return eye, "wall_stand_carriage", {"base_z": top, "post_xy": post, "extension_m": round(ext, 4),
                                            "rise_m": round(rise, 4)}
    raise ValueError(f"exam_cameras.cameras.{name}.mount: unknown mount {mount!r}")


def solve_exam_cameras(cfg: dict, spec: dict, rng) -> list:
    """Poses + optics of the RGB-D exam cameras (cameras.yaml exam_cameras). Low movement coverage goes to
    layout.warnings; a patient closer than the sensor's minimum depth is expected for the top camera and goes to
    layout.notes and the camera's `min_patient_distance_m` / `within_depth_range`."""
    ccfg = cfg.get("cameras") or {}
    ex = exam_cameras_cfg(cfg)
    if not ex:
        return []
    targets = _targets(spec)
    defaults = ex.get("defaults") or {}
    eq = spec["layout"]["equipment"]
    n, _ = detector_axes(eq)
    L, W = spec["footprint_m"]
    H = spec["ceiling_height_m"]
    min_cov = float(ex.get("min_movement_coverage", 0.9))
    warnings = spec["layout"].setdefault("warnings", [])
    notes = spec["layout"].setdefault("notes", [])
    out = []
    for name, own in (ex.get("cameras") or {}).items():
        c = {**defaults, **(own or {})}
        if not c.get("enabled", True):
            continue
        sensor = ccfg["sensors"][c["rig"]]
        portrait = c.get("orientation", "landscape") == "portrait"
        streams = {s: stream_optics(sensor, s, "portrait" if portrait else "landscape")
                   for s in c.get("streams", ["color", "depth"])}
        main = streams.get("depth") or next(iter(streams.values()))
        zone = movement_zone(spec, c, rng)
        eye, attached, info = _exam_mount(spec, cfg, name, c, rng)
        target = _exam_target(spec, cfg, c, targets, zone)
        pj, tj = number(rng, c.get("position_jitter_m", 0.0)), number(rng, c.get("target_jitter_m", 0.0))
        if pj > 0:
            eye = [v + rng.uniform(-pj, pj) for v in eye]
        if tj > 0:
            target = [target[0] + rng.uniform(-tj, tj), target[1] + rng.uniform(-tj, tj), target[2]]
        eye = [min(max(eye[0], 0.05), L - 0.05), min(max(eye[1], 0.05), W - 0.05), min(max(eye[2], 0.05), H - 0.05)]
        if c.get("tilt_deg") is not None:     # look at the target's x, y, pitched tilt_deg below horizontal
            d = math.hypot(target[0] - eye[0], target[1] - eye[1])
            target = [target[0], target[1], eye[2] - d * math.tan(math.radians(number(rng, c["tilt_deg"])))]
        fwd = np.array(target, float) - np.array(eye, float)
        fwd /= np.linalg.norm(fwd)
        # camera stays upright (portrait = tall image via swapped optics); looking down: image top away from the
        # detector, image width along the detector wall (the patient's shoulders)
        up = np.array([0.0, 0.0, 1.0]) if abs(fwd[2]) < 0.95 else np.array([n[0], n[1], 0.0])
        tan_h = math.tan(math.radians(main["fov_h_deg"]) / 2)
        tan_v = math.tan(math.radians(main["fov_v_deg"]) / 2)
        mcov = {"body": round(frame_fraction(eye, fwd, up, zone["body"], tan_h, tan_v), 3),
                "floor": round(frame_fraction(eye, fwd, up, zone["floor"], tan_h, tan_v), 3)}
        key = "floor" if c.get("target") == "patient_top" else "body"
        if mcov[key] < float(c.get("min_movement_coverage", min_cov)):
            warnings.append(f"exam camera {name} frames only {100 * mcov[key]:.0f}% of the patient movement zone ({key})")
        rng_d = (sensor.get("depth") or {}).get("range_m")
        pts = np.concatenate([zone["body"], zone["floor"]])
        near = float(np.min(np.linalg.norm(pts - np.array(eye), axis=1)))
        in_range = not (rng_d and near < rng_d[0])
        if not in_range and "depth" in streams:
            notes.append(f"exam camera {name}: patient can come within {near:.2f} m, closer than the "
                         f"{c['rig']} minimum depth {rng_d[0]:.2f} m (no depth there)")
        entry = {"name": name, "rig": c["rig"], "mount": c["mount"] if isinstance(c["mount"], str) else "fixed",
                 "zone": "exam", "auto_frame": False, "attached_to": attached,
                 "position": [round(float(v), 4) for v in eye], "target": [round(float(v), 4) for v in target],
                 "up": [round(float(v), 4) for v in up], "orientation": "portrait" if portrait else "landscape",
                 "target_name": c["target"] if isinstance(c.get("target"), str) else "fixed",
                 "focal_length_mm": main["focal_length_mm"], "horizontal_aperture_mm": main["horizontal_aperture_mm"],
                 "vertical_aperture_mm": main["vertical_aperture_mm"], "fov_h_deg": main["fov_h_deg"],
                 "fov_v_deg": main["fov_v_deg"], "resolution": main["resolution"],
                 "clipping_range_m": list(sensor.get("clipping_range_m", [0.05, 20.0])),
                 "streams": streams, "depth_range_m": rng_d, "baseline_m": sensor.get("baseline_m"),
                 "body_size_m": list(sensor.get("body_size_m", [0.124, 0.029, 0.026])), "asset": sensor.get("asset"),
                 "stand": bool(c.get("stand", True)) and c.get("stand_type", "none") != "none",
                 "stand_type": c.get("stand_type", "none"), "mount_info": info, "movement_coverage": mcov,
                 "min_patient_distance_m": round(near, 3), "within_depth_range": in_range,
                 "focus_distance_m": round(float(np.linalg.norm(np.array(target) - np.array(eye))), 4),
                 "housing": False}
        if "radius_m" in c and c["mount"] in LATERAL_MOUNTS:
            stand = spec["layout"]["exam_cameras"][name]
            entry.update(radius_m=stand["radius_m"], height_m=stand["height_m"])
        out.append(entry)
    return out
