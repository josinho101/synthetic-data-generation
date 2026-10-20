"""Validation rules for the configuration. Each check appends readable error strings."""

import re

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
FT = 0.3048

WEIGHT_BLOCKS = {
    "detector_side": {"left", "right"},
    "changing_room_corner": {"north", "south"},
    "entrance_wall": {"west", "side"},
    "wall_finish": None,             # keys must exist in materials.walls
    "floor_material": None,          # keys must exist in materials.floors
    "cct_class": None,               # keys must exist in lighting.cct_k
    "patient_support": {"none", "table", "stretcher"},
    "tube_column_type": {"floor", "floor_ceiling"},
}


def footprint_m(room: dict):
    """[length, width] in meters (footprint_m wins over footprint_ft)."""
    if room.get("footprint_m"):
        return [float(v) for v in room["footprint_m"]]
    return [float(v) * FT for v in room.get("footprint_ft") or [0, 0]]


def ceiling_range_m(room: dict):
    """[min, max] room height in meters; a single number means a fixed height (ceiling_height_ft wins)."""
    value, scale = (room.get("ceiling_height_ft"), FT) if room.get("ceiling_height_ft") is not None else \
        (room.get("ceiling_height_m"), 1.0)
    if isinstance(value, (int, float)):
        return [float(value) * scale] * 2
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [float(v) * scale for v in value]
    raise ValueError(f"room height must be a number or [min, max] (got {value!r})")


def _weights(errors, where, block, allowed=None):
    if not isinstance(block, dict) or not block:
        errors.append(f"{where}: must be a non-empty mapping of weights")
        return
    for key, value in block.items():
        if not isinstance(value, (int, float)) or value < 0:
            errors.append(f"{where}.{key}: weight must be a number >= 0 (got {value!r})")
        if allowed is not None and key not in allowed:
            errors.append(f"{where}.{key}: unknown option (allowed {sorted(allowed)})")
    if sum(v for v in block.values() if isinstance(v, (int, float))) <= 0:
        errors.append(f"{where}: at least one weight must be > 0")


def _range(errors, where, value, lo=0.0, hi=float("inf")):
    ok = isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)
    if not ok or not (lo <= value[0] <= value[1] <= hi):
        errors.append(f"{where}: must be [min, max] with {lo} <= min <= max <= {hi} (got {value!r})")


def _colors(errors, where, values):
    values = values if isinstance(values, list) else [values]
    if not values:
        errors.append(f"{where}: needs at least one colour")
    for value in values:
        if not isinstance(value, str) or not _HEX.match(value):
            errors.append(f"{where}: colour must be '#rrggbb' (got {value!r})")


def _validate_variations(errors, cfg):
    var = cfg["variations"]
    if not isinstance(var.get("count"), int) or var["count"] < 1:
        errors.append("variations.count: must be an integer >= 1")
    if not isinstance(var.get("seed"), int):
        errors.append("variations.seed: must be an integer")
    if not isinstance(var.get("randomize_layout", True), bool):
        errors.append("variations.randomize_layout: true | false")
    if var.get("layout_seed") is not None and not isinstance(var["layout_seed"], int):
        errors.append("variations.layout_seed: integer or null")
    allowed_from = {"wall_finish": set(cfg["materials"].get("walls") or {}),
                    "floor_material": set(cfg["materials"].get("floors") or {}),
                    "cct_class": set(cfg["lighting"].get("cct_k") or {})}
    for name, allowed in WEIGHT_BLOCKS.items():
        _weights(errors, f"variations.{name}", var.get(name), allowed if allowed is not None else allowed_from[name])


def _validate_room(errors, cfg):
    room = cfg["room"]
    fp = room.get("footprint_m") or room.get("footprint_ft")
    if not (isinstance(fp, list) and len(fp) == 2 and all(isinstance(v, (int, float)) and v > 0 for v in fp)):
        errors.append("room.footprint_ft / footprint_m: must be [length, width] with positive numbers")
        return
    length, width = footprint_m(room)
    if length < width:
        errors.append(f"room footprint: length ({length:.2f} m) must be >= width ({width:.2f} m)")
    try:
        _range(errors, "room height (ceiling_height_ft / ceiling_height_m, in m)", ceiling_range_m(room), 2.2, 5.0)
    except (ValueError, TypeError) as exc:
        errors.append(f"room.ceiling_height: {exc}")
    _range(errors, "room.entrance.width_m", (room.get("entrance") or {}).get("width_m"), 0.6, 2.0)
    _range(errors, "room.entrance.open_angle_deg", (room.get("entrance") or {}).get("open_angle_deg"), 0, 180)
    cr = room.get("changing_room") or {}
    for key in ("length_m", "depth_m", "door_width_m"):
        _range(errors, f"room.changing_room.{key}", cr.get(key), 0.5, 5.0)
    _range(errors, "room.changing_room.door_open_angle_deg", cr.get("door_open_angle_deg"), 0, 180)
    if cr.get("length_m") and cr["length_m"][0] > 0.5 * length:
        errors.append("room.changing_room.length_m: changing room takes more than half the room length")
    if cr.get("depth_m") and cr["depth_m"][0] > width - 0.9:
        errors.append("room.changing_room.depth_m: leaves less than 0.9 m walkway next to the changing room")


def _validate_equipment(errors, cfg):
    eq = cfg["equipment"]
    ws, tube = eq.get("wall_stand") or {}, eq.get("tube_stand") or {}
    if ws.get("placement", "far_end") not in ("far_end", "random"):
        errors.append("equipment.wall_stand.placement: far_end | random")
    if ws.get("wall", "opposite_checkin") not in ("opposite_checkin", "sampled"):
        errors.append("equipment.wall_stand.wall: opposite_checkin | sampled")
    _range(errors, "equipment.wall_stand.carriage_travel_m", ws.get("carriage_travel_m"), 0.0, 3.0)
    _range(errors, "equipment.wall_stand.detector_center_height_m", ws.get("detector_center_height_m"), 0.0, 3.0)
    travel, height = ws.get("carriage_travel_m") or [0, 0], ws.get("detector_center_height_m") or [0, 0]
    if not (travel[0] <= height[0] and height[1] <= travel[1]):
        errors.append("equipment.wall_stand.detector_center_height_m: must lie inside carriage_travel_m")
    _range(errors, "equipment.tube_stand.sid_m", tube.get("sid_m"), 0.5, 3.0)
    _range(errors, "equipment.tube_stand.rail_length_m", tube.get("rail_length_m"), 0.5, 10.0)
    _range(errors, "equipment.floor_marker.stand_gap_m", (eq.get("floor_marker") or {}).get("stand_gap_m"), 0.0, 1.0)
    _colors(errors, "equipment.floor_marker.tape_colors", (eq.get("floor_marker") or {}).get("tape_colors"))
    em = eq.get("entrance_marker") or {}
    if em.get("enabled", True) and em and not 0.3 <= em.get("distance_from_door_m", -1) <= 1.0:
        errors.append("equipment.entrance_marker.distance_from_door_m: must be in [0.3, 1.0] (stay inside the door "
                      "clearance zone)")
    # SID must fit across the room width (detector on one long wall, tube rail on the other)
    width = footprint_m(cfg["room"])[1]
    sid_max = max_sid(eq, width)
    if tube.get("sid_m") and sid_max < tube["sid_m"][0]:
        errors.append(f"equipment.tube_stand.sid_m: minimum SID {tube['sid_m'][0]} m does not fit in a "
                      f"{width:.2f} m wide room (max {sid_max:.2f} m)")


def detector_face_offset(eq: dict) -> float:
    """Distance of the detector front face from its wall."""
    ws, det = eq["wall_stand"], eq["detector"]
    return ws["wall_gap_m"] + ws["column_size_m"][1] + det["housing_size_m"][2]


def min_focal_offset(eq: dict) -> float:
    """Smallest distance of the focal spot from the tube wall (shortest arm)."""
    t = eq["tube_stand"]
    return t["rail_offset_m"] + t["column_size_m"][1] / 2 + t["arm_min_length_m"] + t["housing_radius_m"]


def max_sid(eq: dict, width: float) -> float:
    return width - detector_face_offset(eq) - min_focal_offset(eq)


def _validate_materials(errors, cfg):
    mat = cfg["materials"]
    for name, spec in (mat.get("walls") or {}).items():
        _colors(errors, f"materials.walls.{name}.colors", (spec or {}).get("colors"))
        _range(errors, f"materials.walls.{name}.roughness", (spec or {}).get("roughness"), 0, 1)
    for name, spec in (mat.get("floors") or {}).items():
        _colors(errors, f"materials.floors.{name}.colors", (spec or {}).get("colors"))
        _range(errors, f"materials.floors.{name}.roughness", (spec or {}).get("roughness"), 0, 1)
    de = mat.get("min_floor_wall_delta_e", 0.0)
    if not isinstance(de, (int, float)) or not 0 <= de <= 60:
        errors.append("materials.min_floor_wall_delta_e: number 0..60")
    if mat.get("glare") not in (mat.get("glare_levels") or {}):
        errors.append(f"materials.glare: '{mat.get('glare')}' is not defined in materials.glare_levels")
    _colors(errors, "materials.equipment.body_colors", (mat.get("equipment") or {}).get("body_colors"))


def _validate_lighting(errors, cfg):
    light = cfg["lighting"]
    lux = light.get("lux") or {}
    if not all(isinstance(lux.get(k), (int, float)) for k in ("mean", "sd", "min", "max")):
        errors.append("lighting.lux: needs mean, sd, min, max")
    elif not (0 < lux["min"] <= lux["mean"] <= lux["max"]) or lux["sd"] <= 0:
        errors.append("lighting.lux: require 0 < min <= mean <= max and sd > 0")
    for name, rng in (light.get("cct_k") or {}).items():
        _range(errors, f"lighting.cct_k.{name}", rng, 1000, 20000)
    panels = light.get("panels") or {}
    _weights(errors, "lighting.panels.size_weights", panels.get("size_weights"), set(panels.get("sizes_m") or {}))
    _range(errors, "lighting.panels.count_exam", panels.get("count_exam"), 1, 20)
    for key in ("indirect_gain", "lux_calibration"):
        if not isinstance(light.get(key), (int, float)) or light[key] <= 0:
            errors.append(f"lighting.{key}: must be a number > 0")


def _validate_props(errors, cfg):
    for name, item in ((cfg["props"].get("items") or {}).items()):
        if "p" in item and not (isinstance(item["p"], (int, float)) and 0 <= item["p"] <= 1):
            errors.append(f"props.items.{name}.p: must be a probability 0..1")
        if "count" in item:
            _range(errors, f"props.items.{name}.count", item["count"], 0, 50)
        if "colors" in item:
            _colors(errors, f"props.items.{name}.colors", item["colors"])


def _number_or_range(errors, where, value, lo=0.0, hi=float("inf"), strict=False):
    """A fixed number or a [min, max] range (sampled per room)."""
    if isinstance(value, (list, tuple)):
        _range(errors, where, value, lo, hi)
    elif not isinstance(value, (int, float)) or isinstance(value, bool) or not (lo <= value <= hi) or \
            (strict and value <= lo):
        errors.append(f"{where}: number or [min, max] {'>' if strict else '>='} {lo} (got {value!r})")


def _validate_sensor(errors, where, sensor):
    if not isinstance(sensor, dict):
        errors.append(f"{where}: must be a mapping")
        return
    for stream in ("color", "depth"):
        st = sensor.get(stream)
        if st is None:
            continue
        fov = st.get("fov_deg")
        if not (isinstance(fov, list) and len(fov) == 2 and all(isinstance(v, (int, float)) and 0 < v < 180 for v in fov)):
            errors.append(f"{where}.{stream}.fov_deg: [horizontal, vertical] in (0, 180)")
        res = st.get("resolution")
        if not (isinstance(res, list) and len(res) == 2 and all(isinstance(v, int) and v > 0 for v in res)):
            errors.append(f"{where}.{stream}.resolution: [width, height] in pixels")
        if st.get("range_m") is not None:
            _range(errors, f"{where}.{stream}.range_m", st["range_m"], 0.0, 1000.0)
        off = st.get("offset_m", [0.0, 0.0, 0.0])
        if not (isinstance(off, list) and len(off) == 3 and all(isinstance(v, (int, float)) for v in off)):
            errors.append(f"{where}.{stream}.offset_m: [right, up, forward] in meters")
    if not (isinstance(sensor.get("horizontal_aperture_mm", 20.955), (int, float)) and
            sensor.get("horizontal_aperture_mm", 20.955) > 0):
        errors.append(f"{where}.horizontal_aperture_mm: number > 0")
    _range(errors, f"{where}.clipping_range_m", sensor.get("clipping_range_m", [0.05, 20.0]), 1e-4, 1e6)


def _validate_exam_cameras(errors, cams):
    from ..layout.cameras import EXAM_MOUNTS, EXAM_TARGETS, STAND_TYPES
    ex = cams.get("exam_cameras")
    if not ex:
        return
    sensors = cams.get("sensors") or {}
    for key, sensor in sensors.items():
        _validate_sensor(errors, f"cameras.sensors.{key}", sensor)
    targets = set(EXAM_TARGETS) | {"room_center", "floor_marker", "detector", "checkin_center", "checkin_door",
                                   "entrance_door"}
    search = ex.get("lateral_search") or {}
    for key in ("angle_step_deg", "footprint_m"):
        if key in search:
            _number_or_range(errors, f"cameras.exam_cameras.lateral_search.{key}", search[key], 0.0, strict=True)
    if "max_swing_deg" in search:
        _number_or_range(errors, "cameras.exam_cameras.lateral_search.max_swing_deg", search["max_swing_deg"], 0.0, 90.0)
    defaults = ex.get("defaults") or {}
    for name, own in (ex.get("cameras") or {}).items():
        c = {**defaults, **(own or {})}
        where = f"cameras.exam_cameras.cameras.{name}"
        if not c.get("enabled", True):
            continue
        rig = c.get("rig")
        if rig not in sensors:
            errors.append(f"{where}.rig: one of the sensors {sorted(sensors)} (got {rig!r})")
        else:
            streams = c.get("streams", ["color", "depth"])
            if not (isinstance(streams, list) and streams and all(sensors[rig].get(s) for s in streams)):
                errors.append(f"{where}.streams: non-empty list of streams defined in cameras.sensors.{rig}")
        mount, target = c.get("mount"), c.get("target")
        if not (mount in EXAM_MOUNTS or (isinstance(mount, list) and len(mount) == 3)):
            errors.append(f"{where}.mount: one of {list(EXAM_MOUNTS)} or [x, y, z] (got {mount!r})")
        if not (target in targets or (isinstance(target, list) and len(target) == 3)):
            errors.append(f"{where}.target: one of {sorted(targets)} or [x, y, z] (got {target!r})")
        if c.get("orientation", "landscape") not in ("landscape", "portrait"):
            errors.append(f"{where}.orientation: landscape | portrait")
        if c.get("stand_type", "none") not in STAND_TYPES:
            errors.append(f"{where}.stand_type: one of {list(STAND_TYPES)}")
        if mount in ("detector_lateral_left", "detector_lateral_right"):
            _number_or_range(errors, f"{where}.radius_m", c.get("radius_m"), 0.0, 20.0, strict=True)
            _number_or_range(errors, f"{where}.height_m", c.get("height_m"), 0.0, 10.0, strict=True)
        if mount == "detector_top":
            _number_or_range(errors, f"{where}.extension_m", c.get("extension_m", 0.2), 0.0, 5.0)
            _number_or_range(errors, f"{where}.rise_m", c.get("rise_m", 0.1), 0.0, 5.0)
        if mount == "tube_head":
            off = c.get("offset_m", [0.0, 0.20, 0.16])
            if not (isinstance(off, list) and len(off) == 3):
                errors.append(f"{where}.offset_m: [along rail, along beam, up] (numbers or [min, max])")
            else:
                for k, v in enumerate(off):
                    _number_or_range(errors, f"{where}.offset_m[{k}]", v, -5.0, 5.0)
        for key in ("position_jitter_m", "target_jitter_m", "movement_margin_m"):
            if key in c:
                _number_or_range(errors, f"{where}.{key}", c[key], 0.0, 5.0)
        if c.get("tilt_deg") is not None:
            _number_or_range(errors, f"{where}.tilt_deg", c["tilt_deg"], -89.0, 89.0)
        if "body_height_m" in c:
            _number_or_range(errors, f"{where}.body_height_m", c["body_height_m"], 0.0, 3.0, strict=True)


def _validate_cameras(errors, cfg):
    from ..placement import FACING
    cams = cfg.get("cameras") or {}
    defaults = cams.get("defaults") or {}
    mounts = {"far_wall_left", "far_wall_right", "checkin_corner", "entrance_outside"}
    targets = {"room_center", "floor_marker", "detector", "checkin_center", "checkin_door", "entrance_door"}
    for name, own in (cams.get("cameras") or {}).items():
        c = {**defaults, **(own or {})}
        where = f"cameras.cameras.{name}"
        mount, target = c.get("mount"), c.get("target")
        if not (mount in mounts or (isinstance(mount, list) and len(mount) == 3)):
            errors.append(f"{where}.mount: one of {sorted(mounts)} or [x, y, z] (got {mount!r})")
        if not (target in targets or (isinstance(target, list) and len(target) == 3)):
            errors.append(f"{where}.target: one of {sorted(targets)} or [x, y, z] (got {target!r})")
        f = c.get("focal_length_mm")
        if isinstance(f, list):
            _range(errors, f"{where}.focal_length_mm", f, 1.0, 300.0)
        elif not (isinstance(f, (int, float)) and f > 0):
            errors.append(f"{where}.focal_length_mm: number or [min, max] > 0")
        res = c.get("resolution")
        if not (isinstance(res, list) and len(res) == 2 and all(isinstance(v, int) and v > 0 for v in res)):
            errors.append(f"{where}.resolution: [width, height] in pixels")
        _range(errors, f"{where}.clipping_range_m", c.get("clipping_range_m"), 1e-4, 1e6)
        for key in ("ceiling_gap_m", "corner_inset_m", "wall_offset_m", "position_jitter_m", "target_jitter_m",
                    "horizontal_aperture_mm"):
            if not isinstance(c.get(key), (int, float)) or c[key] < 0:
                errors.append(f"{where}.{key}: number >= 0")
    cov = cams.get("coverage")
    if cov:
        _range(errors, "cameras.coverage.focal_length_mm", cov.get("focal_length_mm"), 1.0, 300.0)
        for g in (cov.get("weights") or {}):
            if g not in ("marker", "walk_path", "walk_feet", "support", "room"):
                errors.append(f"cameras.coverage.weights.{g}: unknown group")
        for key in ("search_step_m", "walk_spacing_m", "room_grid_m"):
            if not isinstance(cov.get(key), (int, float)) or cov[key] <= 0:
                errors.append(f"cameras.coverage.{key}: number > 0")
    _validate_exam_cameras(errors, cams)
    place = cfg["export"].get("placement") or {}
    if place.get("door_facing", "-Y") not in FACING:
        errors.append(f"export.placement.door_facing: one of {sorted(FACING)}")
    if place.get("origin", "center") not in ("center", "entrance_door", "room_corner"):
        errors.append("export.placement.origin: center | entrance_door | room_corner")


def _validate_export(errors, cfg):
    export = cfg["export"]
    if not export.get("output_root"):
        errors.append("export.output_root: required")
    if not isinstance(export.get("workers"), int) or export["workers"] < 1:
        errors.append("export.workers: must be an integer >= 1")
    if (export.get("usd") or {}).get("file_format") not in ("usd", "usda", "usdc"):
        errors.append("export.usd.file_format: must be usd, usda or usdc")


def validate(cfg: dict) -> list:
    errors = []
    for check in (_validate_variations, _validate_room, _validate_equipment, _validate_materials,
                  _validate_lighting, _validate_props, _validate_cameras, _validate_export):
        try:
            check(errors, cfg)
        except (KeyError, TypeError, IndexError) as exc:
            errors.append(f"{check.__name__[10:]}: missing or malformed setting ({exc!r})")
    return errors
