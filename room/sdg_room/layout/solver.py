"""Layout solver: turns a sampled room spec into floor positions for everything in the room.

Order: check-in room (outside the X-ray room) + connecting door -> entrance (its outer door) -> wall stand (detector) -> tube stand + rail -> floor marker
-> exam-camera tripods -> keep-out zones (door swings, beam corridor, marker, rail) -> table / stretcher -> props -> walk check.
Everything is an axis-aligned rectangle (objects are rotated by multiples of 90 deg). A layout that cannot be
solved raises LayoutError; the manifest then resamples the room.
"""

import logging
import math
import random
from collections import deque

import numpy as np

from ..sampling.distributions import number
from .geometry import WALL_YAW, Rect, WallSegment, footprint_for_yaw

_LOG = logging.getLogger("sdg_room.layout")


def collimator_front(tube: dict) -> float:
    """Distance from the focal spot to the front face of the collimator (towards the detector)."""
    return 0.6 * tube["housing_radius_m"] + tube["collimator_size_m"][1]


LATERAL_MOUNTS = ("detector_lateral_left", "detector_lateral_right")
CHECKIN_DOOR_CLEAR_M = 0.30     # furniture-free strip in front of a door inside the small check-in room (the walk
                                # check from the entrance to the connecting door guarantees passage)


def exam_cameras_cfg(cfg: dict) -> dict:
    """cameras.yaml exam_cameras block, or {} when the exam cameras (or all cameras) are disabled."""
    ccfg = cfg.get("cameras") or {}
    ex = ccfg.get("exam_cameras") or {}
    return ex if ccfg.get("enabled", True) and ex.get("enabled", False) else {}


def detector_axes(equipment: dict):
    """(normal, left): detector normal into the room and the patient's left while facing the detector
    (= the left seen from the tube), both unit 2-D vectors in the room frame."""
    n = equipment["detector"]["normal"]
    return (n[0], n[1]), (n[1], -n[0])


class LayoutError(RuntimeError):
    """The sampled spec has no valid layout (the room is resampled)."""


def transform_point(lx, ly, ox, oy, yaw):
    a = math.radians(yaw)
    return ox + lx * math.cos(a) - ly * math.sin(a), oy + lx * math.sin(a) + ly * math.cos(a)


def transform_rect(local: Rect, ox, oy, yaw) -> Rect:
    pts = [transform_point(x, y, ox, oy, yaw) for x in (local.x0, local.x1) for y in (local.y0, local.y1)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return Rect(min(xs), min(ys), max(xs), max(ys))


def _span_center(lo, hi, width, u, margin):
    """Centre of an opening of `width` placed at fraction u inside [lo + margin, hi - margin]."""
    free = (hi - margin) - (lo + margin) - width
    if free < 0:
        return None
    return lo + margin + width / 2 + u * free


class _Layout:
    def __init__(self, cfg, spec):
        self.cfg, self.spec = cfg, spec
        self.L, self.W = spec["footprint_m"]
        self.H = spec["ceiling_height_m"]
        self.room = Rect(0, 0, self.L, self.W)
        self.obstacles = []   # (name, Rect): block walking and other objects
        self.keepouts = []    # (name, Rect): no objects, walking allowed
        self.warnings = []
        self.notes = []
        self.dropped = []
        self.out = {}

    # --- checks --------------------------------------------------------------------------------
    def in_exam_area(self, rect: Rect) -> bool:
        return rect.inside(self.room) and not rect.overlaps(self.changing_block)

    def free(self, rect: Rect, clearance=0.0, ignore=()) -> bool:
        grown = rect.inflate(clearance)
        return not any(r.overlaps(grown) for n, r in self.obstacles + self.keepouts if n not in ignore)

    # --- check-in / changing room (outside the X-ray room) --------------------------------------
    def changing_room(self):
        """Check-in / changing room OUTSIDE the X-ray room: an annex against the X-ray room's west (entrance-end) wall
        in the north or south corner (x < 0). The patient enters it from the corridor through the outer door
        (`entrance`), changes, and walks into the X-ray room through the connecting door in the shared west wall
        (`changing_room.door`, swings into the X-ray room, inside the door clearance zone)."""
        cr, room = self.spec["changing_room"], self.cfg["room"]
        t, W = room["wall_thickness_m"], self.W
        cl, cd, dw = cr["length_m"], min(cr["depth_m"], self.W), cr["door_width_m"]
        north = self.spec["changing_room_corner"] == "north"
        clr = room["walk"]["door_clearance_m"]
        x0, x1 = -t - cl, -t
        y0, y1 = (W - cd, W) if north else (0.0, cd)
        interior = Rect(x0, y0, x1, y1)
        block = Rect(x0 - t, y0 - t, x1, y1 + t)        # annex with its own walls (shares the X-ray room's west wall)
        c = _span_center(y0, y1, dw, cr["u"], 0.08)
        if c is None:
            raise LayoutError("connecting door does not fit between the check-in room and the X-ray room")
        swing = Rect(0.0, c - dw / 2, dw, c + dw / 2)          # into the X-ray room
        clear = Rect(0.0, c - dw / 2, max(dw, clr), c + dw / 2)  # free zone inside the X-ray room
        inside = Rect(x1 - CHECKIN_DOOR_CLEAR_M, c - dw / 2, x1, c + dw / 2)   # door kept free in the check-in room
        door = {"wall": "west", "axis": "y", "center": [0.0, c], "width": dw, "plane": [-t, 0.0],
                "out_normal": [1, 0], "connects": "xray_room", "height": room["changing_room"]["door_height_m"],
                "hinge": cr["hinge"], "open_angle_deg": cr["door_open_angle_deg"], "swing": swing.as_list()}
        self.keepouts += [("changing_door_clear", clear), ("changing_door_swing", swing)]
        self.annex_keepouts = [("changing_door_inside", inside)]
        self.out["changing_room"] = {"corner": self.spec["changing_room_corner"], "location": "outside_west",
                                     "interior": interior.as_list(), "block": block.as_list(), "door": door,
                                     "point_inside": [x1 - 0.4, c], "point_outside": [0.4, c]}
        self.changing_block, self.changing_interior, self.changing_swing = block, interior, swing

    # --- entrance (outer door of the check-in room) ------------------------------------------------
    def entrance(self):
        """Outer door of the check-in room, from the corridor: the only way into the suite. 'west' = the check-in
        room's west wall, 'side' = its outer long wall (in line with the X-ray room's north / south wall); the other
        wall is used when the door does not fit. It swings out into the corridor."""
        ent, room = self.spec["entrance"], self.cfg["room"]
        t = room["wall_thickness_m"]
        w_req, m = ent["width_m"], room["entrance"]["edge_margin_m"]
        w_min = float(room["entrance"].get("min_width_m", 0.81))
        it, north = self.changing_interior, self.spec["changing_room_corner"] == "north"
        order = ["west", "side"] if self.spec["entrance_wall"] == "west" else ["side", "west"]
        door = None
        for k, wall in enumerate(order):
            lo, hi = (it.y0, it.y1) if wall == "west" else (it.x0, it.x1)
            w = min(w_req, hi - lo - 2 * m - 1e-6)   # narrowed to the wall when the sampled door is wider
            if w < w_min - 1e-9:
                continue
            if wall == "west":
                c = _span_center(it.y0, it.y1, w, ent["u"], m)
                if c is None:
                    continue
                door = {"wall": "west", "axis": "y", "center": [it.x0, c], "width": w, "plane": [it.x0 - t, it.x0],
                        "out_normal": [-1, 0]}
                swing = Rect(it.x0 - t - w, c - w / 2, it.x0 - t, c + w / 2)
                clear = Rect(it.x0, c - w / 2, it.x0 + CHECKIN_DOOR_CLEAR_M, c + w / 2)
                start = (it.x0 + 0.35, c)
            else:
                c = _span_center(it.x0, it.x1, w, ent["u"], m)
                if c is None:
                    continue
                y, sgn = (it.y1, 1) if north else (it.y0, -1)          # sgn: outward
                door = {"wall": "north" if north else "south", "axis": "x", "center": [c, y], "width": w,
                        "plane": sorted([y, y + sgn * t]), "out_normal": [0, sgn]}
                swing = Rect(c - w / 2, min(y + sgn * t, y + sgn * (t + w)), c + w / 2, max(y + sgn * t, y + sgn * (t + w)))
                depth = CHECKIN_DOOR_CLEAR_M
                clear = Rect(c - w / 2, min(y, y - sgn * depth), c + w / 2, max(y, y - sgn * depth))
                start = (c, y - sgn * 0.35)
            if k:
                self.notes.append(f"entrance does not fit on the {order[0]} wall of the check-in room: {wall} wall used")
            break
        if door is None:
            raise LayoutError("entrance does not fit on the check-in room")
        if w < w_req - 1e-9:
            self.notes.append(f"entrance narrowed from {w_req:.2f} m to {w:.2f} m to fit the check-in room wall")
        door.update(height=room["entrance"]["height_m"], hinge=ent["hinge"], open_angle_deg=ent["open_angle_deg"],
                    swing=swing.as_list(), placed_on=wall, swings="out", width_sampled_m=w_req)
        self.keepouts.append(("entrance_swing", swing))
        self.annex_keepouts.append(("entrance_clear", clear))
        self.out["entrance"] = door
        self.out["checkin_start"] = list(start)                       # just inside the outer door
        self.out["walk_start"] = list(self.out["changing_room"]["point_outside"])   # X-ray room, at the connecting door
        self._entrance_marker(self.out["changing_room"]["door"])

    def _entrance_marker(self, door):
        """Where the patient first stands still just inside the X-ray room (past the connecting door from the
        check-in room), facing into the room (local -Y)."""
        em = self.cfg["equipment"].get("entrance_marker") or {}
        if not em.get("enabled", True):
            self.out["entrance_marker"] = None
            return
        nx, ny = {"west": (1.0, 0.0), "south": (0.0, 1.0), "north": (0.0, -1.0)}[door["wall"]]
        d = em["distance_from_door_m"]
        px, py = door["center"][0] + nx * d, door["center"][1] + ny * d
        yaw = (math.degrees(math.atan2(ny, nx)) + 90.0) % 360.0      # local -Y -> inward door normal
        ow, od = self.cfg["equipment"]["floor_marker"]["outline_size_m"]
        outline = transform_rect(Rect(-ow / 2, -od / 2, ow / 2, od / 2), px, py, yaw)
        self.out["entrance_marker"] = {"outline": outline.as_list(), "stand_point": [px, py], "yaw_deg": yaw}

    # --- equipment -------------------------------------------------------------------------------
    def _wall_block_x(self, wall_name: str) -> float:
        """Smallest x on a long wall of the X-ray room that objects can use (the check-in room and its doors are
        outside the X-ray room, so the whole wall; door zones are checked separately)."""
        return 0.0

    def equipment(self):
        eq, e = self.cfg["equipment"], self.spec["equipment"]
        ws, det, hd, tube = eq["wall_stand"], eq["detector"], eq["handles"], eq["tube_stand"]
        det_wall = "north" if self.spec["detector_side"] == "left" else "south"
        tube_wall = "south" if det_wall == "north" else "north"
        d_face = e["detector_face_offset_m"]

        # wall stand: local frame = wall at y=0, +y into the room
        half_w = max(ws["base_size_m"][0] / 2, det["housing_size_m"][0] / 2 + hd["standoff_m"] + 2 * hd["bar_radius_m"])
        depth = max(ws["base_size_m"][1], d_face)
        lo = self._wall_block_x(det_wall) + max(ws["x_margin_m"], half_w)
        hi = self.L - max(ws["x_margin_m"], half_w)
        if hi < lo:
            raise LayoutError("no room for the wall stand on the detector wall")
        reach = self._lateral_reach(d_face, e["stand_gap_m"])
        if reach > 0:   # keep the side-on exam-camera tripods inside the room when the wall is long enough
            r_lo, r_hi = max(lo, self._wall_block_x(det_wall) + reach), min(hi, self.L - reach)
            if r_lo <= r_hi:
                lo, hi = r_lo, r_hi
        if self.spec["patient_support"] == "none":
            det_x = lo + e["detector_x_u"] * (hi - lo)
        else:   # keep a long free stretch for the table / stretcher: stand close to the far end wall
            det_x = max(lo, hi - e["detector_x_u"] * 0.6)
        wall_y = 0.0 if det_wall == "south" else self.W
        yaw_d = WALL_YAW[det_wall]
        stand_rect = transform_rect(Rect(-half_w, 0, half_w, depth), det_x, wall_y, yaw_d)

        # tube stand: local frame = tube wall at y=0, +y towards the detector
        sid = e["sid_m"]
        f_off = self.W - d_face - sid
        arm = f_off - tube["rail_offset_m"] - tube["column_size_m"][1] / 2 - tube["housing_radius_m"]
        if arm < tube["arm_min_length_m"] - 1e-6:
            raise LayoutError(f"SID {sid:.2f} m does not fit across the room")
        r_lo, r_hi = self._wall_block_x(tube_wall) + 0.02, self.L - 0.02
        rail_len = min(e["rail_length_m"], r_hi - r_lo)
        c_lo = max(r_lo + rail_len / 2, det_x - rail_len / 2 + 0.25)
        c_hi = min(r_hi - rail_len / 2, det_x + rail_len / 2 - 0.25)
        if c_hi < c_lo:
            raise LayoutError("tube rail cannot reach the wall-stand position")
        rail_cx = c_lo + e["rail_shift_u"] * (c_hi - c_lo)
        tube_y = 0.0 if tube_wall == "south" else self.W
        yaw_t = WALL_YAW[tube_wall]
        carriage_x = det_x - rail_cx                      # along the rail, in the tube-stand frame
        if yaw_t == 180.0:
            carriage_x = -carriage_x
        cw, cdp = tube["carriage_size_m"][0], tube["carriage_size_m"][1]
        coll_d = collimator_front(tube)
        half_t = max(cw / 2, tube["housing_length_m"] / 2)
        tube_local = Rect(carriage_x - half_t, max(0.0, tube["rail_offset_m"] - cdp / 2),
                          carriage_x + half_t, f_off + coll_d)
        tube_rect = transform_rect(tube_local, rail_cx, tube_y, yaw_t)
        rail_strip = transform_rect(Rect(-rail_len / 2, 0, rail_len / 2,
                                         tube["rail_offset_m"] + max(tube["rail_size_m"][0], cdp) / 2 + 0.02),
                                    rail_cx, tube_y, yaw_t)

        # beam corridor between the detector face and the collimator
        face_y = d_face if det_wall == "south" else self.W - d_face
        focal_y = f_off if tube_wall == "south" else self.W - f_off
        coll_y = focal_y + (coll_d if tube_wall == "south" else -coll_d)
        hb = eq["beam_corridor_half_width_m"]
        corridor = Rect(det_x - hb, min(face_y, coll_y), det_x + hb, max(face_y, coll_y))

        # floor marker: patient stands facing the detector
        mk = eq["floor_marker"]
        ow, od = mk["outline_size_m"]
        m_local = Rect(-ow / 2, d_face + e["stand_gap_m"], ow / 2, d_face + e["stand_gap_m"] + od)
        marker_rect = transform_rect(m_local, det_x, wall_y, yaw_d)
        if marker_rect.overlaps(tube_rect):
            raise LayoutError("floor marker overlaps the tube stand")
        stand_xy = (marker_rect.cx, marker_rect.cy)

        for name, rect in (("wall_stand", stand_rect), ("tube_stand", tube_rect)):
            if not self.in_exam_area(rect) or not self.free(rect):
                raise LayoutError(f"{name} collides with a door zone or the changing room")
        self.obstacles += [("wall_stand", stand_rect), ("tube_stand", tube_rect)]
        self.keepouts += [("beam_corridor", corridor), ("floor_marker", marker_rect.inflate(0.3)),
                          ("tube_rail", rail_strip)]
        self.out["equipment"] = {
            "detector_wall": det_wall, "tube_wall": tube_wall,
            "wall_stand": {"origin": [det_x, wall_y], "yaw_deg": yaw_d, "footprint": stand_rect.as_list(),
                           "column_height_m": e["wall_stand_column_height_m"],
                           "detector_center_height_m": e["detector_center_height_m"], "top_bar": e["top_bar"]},
            "detector": {"center": [det_x, face_y, e["detector_center_height_m"]],
                         "normal": [0.0, 1.0 if det_wall == "south" else -1.0, 0.0], "face_offset_m": d_face},
            "tube_stand": {"origin": [rail_cx, tube_y], "yaw_deg": yaw_t, "rail_length_m": rail_len,
                           "carriage_x_m": carriage_x, "arm_length_m": arm, "focal_offset_m": f_off,
                           "column_type": self.spec["tube_column_type"],
                           "column_height_m": e["tube_column_height_m"], "footprint": tube_rect.as_list(),
                           "rail_strip": rail_strip.as_list()},
            "focal_spot": [det_x, focal_y, e["detector_center_height_m"]],
            "beam_axis": [0.0, 1.0 if focal_y < face_y else -1.0, 0.0],
            "sid_m": sid, "beam_corridor": corridor.as_list(),
        }
        self.out["marker"] = {"outline": marker_rect.as_list(), "stand_point": list(stand_xy),
                              "yaw_deg": yaw_d, "tape_color": e["tape_color"]}
        self.det_wall, self.tube_wall, self.det_x = det_wall, tube_wall, det_x

    def _lateral_reach(self, d_face, stand_gap) -> float:
        """Distance along the detector wall from the detector centre to the outer edge of a side-on exam-camera
        tripod (0 when there are none)."""
        ex = exam_cameras_cfg(self.cfg)
        if not ex:
            return 0.0
        defaults, reach = ex.get("defaults") or {}, 0.0
        d_stand = stand_gap + self.cfg["equipment"]["floor_marker"]["outline_size_m"][1] / 2
        half = float((ex.get("lateral_search") or {}).get("footprint_m", 0.55)) / 2
        for own in (ex.get("cameras") or {}).values():
            c = {**defaults, **(own or {})}
            if c.get("enabled", True) and c.get("mount") in LATERAL_MOUNTS:
                r = c["radius_m"]
                r = max(r) if isinstance(r, (list, tuple)) else float(r)
                reach = max(reach, math.sqrt(max(r * r - d_stand * d_stand, 0.0)) + half + 0.05)
        return reach

    # --- exam camera tripods ----------------------------------------------------------------------
    def exam_camera_stands(self):
        """Tripods of the lateral exam cameras (cameras.yaml exam_cameras): radius_m (horizontal) from the detector
        centre, side-on to the patient on the floor marker. A blocked spot (wall, changing room, door zone,
        beam corridor, walk path) is swung around the detector centre at the same radius."""
        ex = exam_cameras_cfg(self.cfg)
        self.out["exam_cameras"] = {}
        if not ex:
            return
        rng = random.Random(f"{self.spec['seed']}:{self.spec.get('attempt', 0)}:exam_stands")
        search = ex.get("lateral_search") or {}
        step = math.radians(float(search.get("angle_step_deg", 10.0)))
        max_swing = math.radians(float(search.get("max_swing_deg", 80.0)))
        half = float(search.get("footprint_m", 0.55)) / 2
        cx, cy = self.out["equipment"]["detector"]["center"][:2]
        n, left = detector_axes(self.out["equipment"])
        sx, sy = self.out["marker"]["stand_point"]
        d_stand = (sx - cx) * n[0] + (sy - cy) * n[1]       # detector face -> patient standing line
        defaults = ex.get("defaults") or {}
        for name, own in (ex.get("cameras") or {}).items():
            c = {**defaults, **(own or {})}
            if not c.get("enabled", True) or c.get("mount") not in LATERAL_MOUNTS:
                continue
            side = 1.0 if c["mount"].endswith("left") else -1.0
            radius, height = number(rng, c["radius_m"]), number(rng, c["height_m"])
            theta0 = math.asin(min(max(d_stand / radius, 0.0), 1.0))   # angle from the detector face plane
            k_max = int(max_swing / step + 1e-9) if step > 0 else 0
            thetas = sorted({round(theta0 + k * step, 9) for k in range(-k_max, k_max + 1)
                             if 0.0 <= theta0 + k * step < math.pi / 2}, key=lambda t: abs(t - theta0))
            for theta in thetas:
                px = cx + radius * (side * left[0] * math.cos(theta) + n[0] * math.sin(theta))
                py = cy + radius * (side * left[1] * math.cos(theta) + n[1] * math.sin(theta))
                rect = Rect.centered(px, py, 2 * half, 2 * half)
                key = f"camera_stand_{name}"
                if not self.in_exam_area(rect) or not self.free(rect, 0.05):
                    continue
                if not self.walk_ok(extra=[(key, rect)]):
                    continue
                self.obstacles.append((key, rect))
                swing = math.degrees(theta - theta0)
                if abs(swing) > 1e-6:
                    self.notes.append(f"{name}: side-on tripod spot blocked, swung {swing:+.0f} deg around the detector")
                self.out["exam_cameras"][name] = {
                    "mount": c["mount"], "side": "left" if side > 0 else "right",
                    "position": [round(px, 4), round(py, 4), round(height, 4)],
                    "radius_m": round(radius, 4), "height_m": round(height, 4),
                    "angle_deg": round(math.degrees(theta), 3), "swing_deg": round(swing, 3),
                    "stand_rect": rect.as_list()}
                break
            else:
                raise LayoutError(f"no free tripod spot for exam camera {name} at {radius:.2f} m from the detector")

    # --- wall segments ---------------------------------------------------------------------------
    def exam_segments(self):
        L, W = self.L, self.W
        segs = [WallSegment("south", "x", 0.0, 0.0, L, (0, 1)), WallSegment("north", "x", W, 0.0, L, (0, -1)),
                WallSegment("west", "y", 0.0, 0.0, W, (1, 0)), WallSegment("east", "y", L, 0.0, W, (-1, 0))]
        return segs

    # --- walk check ------------------------------------------------------------------------------
    def walk_ok(self, extra=()) -> bool:
        """X-ray room: from the connecting door (check-in room -> X-ray room) to the floor marker."""
        cr = self.out["changing_room"]
        return self._reachable(self.room, self.obstacles + list(extra), self.out["walk_start"],
                               [cr["point_outside"], self.out["marker"]["stand_point"]])

    def checkin_walk_ok(self, extra=()) -> bool:
        """Check-in room: from the outer door to the connecting door, around the bench / chair."""
        it = self.changing_interior
        rects = [(n, r) for n, r in self.obstacles + list(extra) if r.overlaps(it)]
        return self._reachable(it, rects, self.out["checkin_start"], [self.out["changing_room"]["point_inside"]])

    def _reachable(self, area: Rect, rects, start, goals) -> bool:
        walk = self.cfg["room"]["walk"]
        g, r = walk["grid_m"], walk["agent_radius_m"]
        xs = np.arange(area.x0 + g / 2, area.x1, g)
        ys = np.arange(area.y0 + g / 2, area.y1, g)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        blocked = (X < area.x0 + r) | (Y < area.y0 + r) | (X > area.x1 - r) | (Y > area.y1 - r)
        for _, rect in rects:
            dx = np.maximum(np.maximum(rect.x0 - X, 0.0), X - rect.x1)
            dy = np.maximum(np.maximum(rect.y0 - Y, 0.0), Y - rect.y1)
            blocked |= dx * dx + dy * dy < r * r

        def cell(p):
            return (min(max(int((p[0] - area.x0) / g), 0), len(xs) - 1),
                    min(max(int((p[1] - area.y0) / g), 0), len(ys) - 1))

        start = cell(start)
        if blocked[start]:
            return False
        seen = np.zeros_like(blocked)
        seen[start] = True
        queue = deque([start])
        while queue:
            i, j = queue.popleft()
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ni, nj = i + di, j + dj
                if 0 <= ni < len(xs) and 0 <= nj < len(ys) and not seen[ni, nj] and not blocked[ni, nj]:
                    seen[ni, nj] = True
                    queue.append((ni, nj))
        for gx, gy in goals:
            near = (X - gx) ** 2 + (Y - gy) ** 2 <= 0.35 ** 2
            if not (seen & near).any():
                return False
        return True

    # --- changing room furniture ------------------------------------------------------------------
    def changing_furniture(self, rng):
        cr, room = self.spec["changing_room"], self.cfg["room"]["changing_room"]
        it, north = self.changing_interior, self.spec["changing_room_corner"] == "north"
        segs = {"west": WallSegment("west", "y", it.x0, it.y0, it.y1, (1, 0)),
                "east": WallSegment("east", "y", it.x1, it.y0, it.y1, (-1, 0)),
                "outer": (WallSegment("outer", "x", it.y1, it.x0, it.x1, (0, -1)) if north else
                          WallSegment("outer", "x", it.y0, it.x0, it.x1, (0, 1))),
                "inner": (WallSegment("inner", "x", it.y0, it.x0, it.x1, (0, 1)) if north else
                          WallSegment("inner", "x", it.y1, it.x0, it.x1, (0, -1)))}
        door_walls = {"east", "west" if self.out["entrance"]["placed_on"] == "west" else "outer"}
        candidates = [n for n in ("west", "outer", "inner", "east") if n not in door_walls]
        zones = [r for _, r in self.annex_keepouts]
        bench = None
        depth = room["bench_depth_m"]
        for name in candidates:
            seg = segs[name]
            length = seg.hi - seg.lo - 0.04
            while length >= 0.6 and bench is None:
                for along in np.linspace(seg.lo + length / 2 + 0.02, seg.hi - length / 2 - 0.02, 5):
                    rect = seg.place(float(along), length, depth)
                    if rect.inside(it) and not any(rect.overlaps(z) for z in zones) and \
                            self.checkin_walk_ok(extra=[("bench", rect)]):
                        bench = {"wall": name, "rect": rect.as_list(), "yaw_deg": seg.yaw, "length_m": length,
                                 "depth_m": depth, "height_m": room["bench_height_m"], "color": cr["bench_color"]}
                        break
                length -= 0.1
            if bench:
                break
        if bench is None:
            raise LayoutError("no space for the bench in the check-in room")
        bench_rect = Rect.from_list(bench["rect"])
        self.obstacles.append(("bench", bench_rect))
        others = [n for n in candidates if n != bench["wall"]] or candidates
        rng.shuffle(others)

        def wall_item(name, width, z, height):
            seg = segs[name]
            span = seg.hi - seg.lo
            width = min(width, span - 0.1)
            along = seg.lo + span / 2 + rng.uniform(-1, 1) * max(0.0, (span - width) / 2 - 0.05)
            return {"wall": name, "along": along, "width_m": width, "z_m": z, "height_m": height,
                    "yaw_deg": seg.yaw, "coord": seg.coord, "axis": seg.axis}

        bench_seg = segs[bench["wall"]]
        hooks = {"wall": bench["wall"], "count": cr["hooks"], "z_m": 1.65, "yaw_deg": bench_seg.yaw,
                 "axis": bench_seg.axis, "coord": bench_seg.coord,
                 "along": [(Rect.from_list(bench["rect"]).cx if bench_seg.axis == "x" else bench_rect.cy)
                           + (k - (cr["hooks"] - 1) / 2) * 0.22 for k in range(cr["hooks"])]}
        shelf_cfg = self.cfg["props"]["changing_room"]["shelf_size_m"]
        shelf = wall_item(others[0], shelf_cfg[0], 1.30, 0.03)
        shelf["depth_m"] = shelf_cfg[1]
        shelf["gown_colors"] = cr["gown_colors"]
        mirror = wall_item(others[1 % len(others)], 0.40, 1.00, 0.80) if cr["mirror"] else None
        if mirror and mirror["wall"] == shelf["wall"]:
            mirror = None if len(others) < 2 else wall_item(others[1], 0.40, 1.00, 0.80)
        chair = None
        if cr["chair"]:
            size = self.cfg["props"]["items"]["chair"]["size_m"]
            for _ in range(30):
                yaw = rng.choice([0.0, 90.0, 180.0, -90.0])
                wx, wy = footprint_for_yaw(size[0], size[1], yaw)
                x = rng.uniform(it.x0 + wx / 2, it.x1 - wx / 2) if it.sx > wx else None
                y = rng.uniform(it.y0 + wy / 2, it.y1 - wy / 2) if it.sy > wy else None
                if x is None or y is None:
                    break
                rect = Rect.centered(x, y, wx, wy)
                if not any(rect.overlaps(z.inflate(0.05)) for z in zones) and not rect.overlaps(bench_rect.inflate(0.05)) \
                        and self.checkin_walk_ok(extra=[("cr_chair", rect)]):
                    chair = {"rect": rect.as_list(), "yaw_deg": yaw,
                             "color": rng.choice(self.cfg["props"]["items"]["chair"]["colors"])}
                    self.obstacles.append(("changing_chair", rect))
                    break
        self.out["changing_room"].update(bench=bench, hooks=hooks, shelf=shelf, mirror=mirror, chair=chair)

    # --- free / wall props ------------------------------------------------------------------------
    def _try_place(self, rng, name, size, wall, yaws=None, tries=60, clearance=None):
        clearance = self.cfg["props"]["clearance_m"] if clearance is None else clearance
        segs = self.exam_segments()
        for _ in range(tries):
            if wall:
                seg = rng.choice(segs)
                yaw = seg.yaw
                wx, _ = footprint_for_yaw(size[0], size[1], yaw)
                half = wx / 2 if seg.axis == "x" else footprint_for_yaw(size[0], size[1], yaw)[1] / 2
                if seg.hi - seg.lo < 2 * half:
                    continue
                rect = seg.place(rng.uniform(seg.lo + half, seg.hi - half), size[0], size[1])
            else:
                yaw = rng.choice(yaws or [0.0, 90.0, 180.0, -90.0])
                wx, wy = footprint_for_yaw(size[0], size[1], yaw)
                rect = Rect.centered(rng.uniform(wx / 2, self.L - wx / 2), rng.uniform(wy / 2, self.W - wy / 2), wx, wy)
            if not self.in_exam_area(rect) or not self.free(rect, clearance):
                continue
            if not self.walk_ok(extra=[(name, rect)]):
                continue
            self.obstacles.append((name, rect))
            return {"rect": rect.as_list(), "yaw_deg": yaw, "center": [rect.cx, rect.cy], "size_m": list(size)}
        return None

    def patient_support(self, rng):
        kind = self.spec["patient_support"]
        self.out["patient_support"] = None
        if kind == "none":
            return
        sup = self.cfg["props"]["patient_support"][kind]
        for size in [sup["size_m"]] + sup.get("alternatives", []):
            placed = self._try_place(rng, kind, size, wall=False, yaws=[0.0, 180.0], tries=120, clearance=0.10)
            if placed:
                placed.update(kind=kind, color=self.spec["support_color"], pad_color=self.spec["support_pad_color"])
                self.out["patient_support"] = placed
                return
        self.notes.append(f"{kind} does not fit in the exam area: dropped")
        self.dropped.append(kind)

    def props(self, rng):
        items_cfg = self.cfg["props"]["items"]
        order = ["generator_cabinet", "lead_screen", "apron_rack", "chair", "waste_bin", "step_stool"]
        wanted = sorted(self.spec["props_requested"], key=lambda p: order.index(p["kind"]) if p["kind"] in order else 99)
        placed = []
        for item in wanted:
            icfg = items_cfg[item["kind"]]
            pos = self._try_place(rng, item["name"], icfg["size_m"], wall=icfg.get("wall", False))
            if pos is None:
                self.notes.append(f"{item['name']} could not be placed: dropped")
                self.dropped.append(item["name"])
                continue
            pos.update(item)
            placed.append(pos)
        self.out["props"] = placed

    def cable_runs(self):
        runs, spec = [], self.spec.get("cable_runs")
        if not spec or spec["count"] < 1:
            self.out["cable_runs"] = runs
            return
        t = self.out["equipment"]["tube_stand"]
        strip = Rect.from_list(t["rail_strip"])
        rail_y = t["origin"][1] + (1 if self.tube_wall == "south" else -1) * self.cfg["equipment"]["tube_stand"]["rail_offset_m"]
        if self.L - strip.x1 > 0.10:
            runs.append({"type": "floor_cover", "points": [[strip.x1, rail_y], [self.L, rail_y]]})
        else:
            lo = self._wall_block_x(self.tube_wall)
            if strip.x0 - lo > 0.10:
                runs.append({"type": "floor_cover", "points": [[strip.x0, rail_y], [lo, rail_y]]})
        if spec["count"] >= 2:
            ws = self.out["equipment"]["wall_stand"]
            fp = Rect.from_list(ws["footprint"])
            y = ws["origin"][1]
            for x in (fp.x1 + 0.12, fp.x0 - 0.12):
                rect = Rect(x - 0.04, min(y, y + (0.05 if y == 0 else -0.05)), x + 0.04, max(y, y + (0.05 if y == 0 else -0.05)))
                if self.in_exam_area(rect) and self.free(rect, ignore=("beam_corridor",)):
                    self.obstacles.append(("wall_conduit", rect))
                    runs.append({"type": "wall_conduit", "rect": rect.as_list(), "wall": self.det_wall})
                    break
        for run in runs:
            run["color"] = spec["color"]
        self.out["cable_runs"] = runs

    # --- lights ----------------------------------------------------------------------------------
    def lights(self):
        light = self.cfg["lighting"]["panels"]
        sx, sy = light["sizes_m"][self.spec["panel_size"]]
        x_lo, x_hi = 0.0, self.L
        avail = x_hi - x_lo
        n = max(1, min(self.spec["panel_count"], int(avail // (sx + 0.3))))
        if n < self.spec["panel_count"]:
            self.notes.append(f"only {n} of {self.spec['panel_count']} ceiling panels fit along the exam area")
        panels = [{"name": f"Panel_{i + 1:02d}", "center": [x_lo + (i + 0.5) * avail / n, self.W / 2], "size_m": [sx, sy],
                   "zone": "exam"} for i in range(n)]
        it = self.changing_interior
        csz = light["sizes_m"]["2x2"]
        panels.append({"name": "Panel_Changing", "center": [it.cx, it.cy],
                       "size_m": [min(csz[0], it.sx - 0.2), min(csz[1], it.sy - 0.2)], "zone": "changing"})
        self.out["panels"] = panels


def solve_layout(cfg: dict, spec: dict, rng) -> dict:
    lay = _Layout(cfg, spec)
    lay.changing_room()
    lay.entrance()
    lay.equipment()
    lay.exam_camera_stands()
    if not lay.walk_ok():
        raise LayoutError("walk path connecting door -> floor marker is blocked by the equipment")
    lay.changing_furniture(rng)
    lay.patient_support(rng)
    lay.props(rng)
    lay.cable_runs()
    lay.lights()
    if not lay.walk_ok():
        raise LayoutError("walk path blocked after placing the props")
    out = lay.out
    out["obstacles"] = {n: r.as_list() for n, r in lay.obstacles}
    out["keepouts"] = {n: r.as_list() for n, r in lay.keepouts}
    out["warnings"] = lay.warnings
    out["notes"] = lay.notes
    out["dropped"] = lay.dropped
    out["walk_ok"] = True
    return out
