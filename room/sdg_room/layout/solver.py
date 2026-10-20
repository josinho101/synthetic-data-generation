"""Layout solver: turns a sampled room spec into floor positions for everything in the room.

Order: changing room + its door -> entrance -> wall stand (detector) -> tube stand + rail -> floor marker
-> keep-out zones (door swings, beam corridor, marker, rail) -> table / stretcher -> props -> walk check.
Everything is an axis-aligned rectangle (objects are rotated by multiples of 90 deg). A layout that cannot be
solved raises LayoutError; the manifest then resamples the room.
"""

import logging
import math
from collections import deque

import numpy as np

from .geometry import WALL_YAW, Rect, WallSegment, footprint_for_yaw

_LOG = logging.getLogger("sdg_room.layout")


def collimator_front(tube: dict) -> float:
    """Distance from the focal spot to the front face of the collimator (towards the detector)."""
    return 0.6 * tube["housing_radius_m"] + tube["collimator_size_m"][1]


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

    # --- changing room -------------------------------------------------------------------------
    def changing_room(self):
        cr, room = self.spec["changing_room"], self.cfg["room"]
        pt, L, W = room["partition_thickness_m"], self.L, self.W
        cl, cd, dw = cr["length_m"], cr["depth_m"], cr["door_width_m"]
        north = self.spec["changing_room_corner"] == "north"
        clr = room["walk"]["door_clearance_m"]
        if north:
            interior, block = Rect(0, W - cd, cl, W), Rect(0, W - cd - pt, cl + pt, W)
            inner = Rect(0, W - cd - pt, cl, W - cd)
        else:
            interior, block = Rect(0, 0, cl, cd), Rect(0, 0, cl + pt, cd + pt)
            inner = Rect(0, cd, cl, cd + pt)
        east = Rect(cl, block.y0, cl + pt, block.y1)
        self.changing_block = block
        margin = 0.08
        wall = self.spec["changing_door_wall"]
        if wall == "east":
            c = _span_center(interior.y0, interior.y1, dw, cr["u"], margin)
            if c is None:
                raise LayoutError("changing door does not fit on the east partition")
            door = {"wall": "east", "axis": "y", "center": [cl + pt / 2, c], "width": dw, "plane": [cl, cl + pt],
                    "out_normal": [1, 0]}
            swing = Rect(cl - dw, c - dw / 2, cl, c + dw / 2)
            clear = Rect(cl + pt, c - dw / 2, cl + pt + clr, c + dw / 2)
            p_out, p_in = (cl + pt + 0.4, c), (cl - 0.4, c)
            parts = [Rect(cl, east.y0, cl + pt, c - dw / 2), Rect(cl, c + dw / 2, cl + pt, east.y1), inner]
        else:
            c = _span_center(0, cl, dw, cr["u"], margin)
            if c is None:
                raise LayoutError("changing door does not fit on the inner partition")
            y_out = inner.y0 if north else inner.y1
            door = {"wall": "inner", "axis": "x", "center": [c, inner.cy], "width": dw, "plane": [inner.y0, inner.y1],
                    "out_normal": [0, -1 if north else 1]}
            if north:
                swing = Rect(c - dw / 2, inner.y1, c + dw / 2, inner.y1 + dw)
                clear = Rect(c - dw / 2, y_out - clr, c + dw / 2, y_out)
            else:
                swing = Rect(c - dw / 2, inner.y0 - dw, c + dw / 2, inner.y0)
                clear = Rect(c - dw / 2, y_out, c + dw / 2, y_out + clr)
            sgn = -1 if north else 1
            p_out, p_in = (c, y_out + sgn * 0.4), (c, (inner.y1 if north else inner.y0) - sgn * 0.4)
            parts = [Rect(0, inner.y0, c - dw / 2, inner.y1), Rect(c + dw / 2, inner.y0, cl, inner.y1), east]
        if swing.sx > interior.sx + 1e-6 or swing.sy > interior.sy + 1e-6:
            raise LayoutError("changing door swing larger than the changing room")
        door.update(height=room["changing_room"]["door_height_m"], hinge=cr["hinge"],
                    open_angle_deg=cr["door_open_angle_deg"], swing=swing.as_list())
        for i, rect in enumerate(parts):
            if rect.sx > 1e-6 and rect.sy > 1e-6:
                self.obstacles.append((f"partition_{i}", rect))
        self.keepouts += [("changing_door_clear", clear), ("changing_door_swing", swing)]
        self.out["changing_room"] = {"corner": self.spec["changing_room_corner"], "interior": interior.as_list(),
                                     "block": block.as_list(), "partition_east": east.as_list(),
                                     "partition_inner": inner.as_list(), "door": door,
                                     "point_inside": list(p_in), "point_outside": list(p_out)}
        self.changing_interior = interior
        self.changing_swing = swing

    # --- entrance --------------------------------------------------------------------------------
    def entrance(self):
        ent, room = self.spec["entrance"], self.cfg["room"]
        w, m, clr = ent["width_m"], room["entrance"]["edge_margin_m"], room["walk"]["door_clearance_m"]
        block, north_cr = self.changing_block, self.spec["changing_room_corner"] == "north"
        wall = self.spec["entrance_wall"]
        door = None
        if wall == "west":
            lo, hi = (0.0, block.y0) if north_cr else (block.y1, self.W)
            c = _span_center(lo, hi, w, ent["u"], m)
            if c is not None:
                door = {"wall": "west", "axis": "y", "center": [0.0, c], "width": w}
                swing, clear = Rect(0, c - w / 2, w, c + w / 2), Rect(0, c - w / 2, max(w, clr), c + w / 2)
                start = (0.4, c)
            else:
                self.notes.append("entrance does not fit on the west wall next to the changing room: long wall used")
                wall = "long_wall"
        if wall == "long_wall":
            side = "south" if north_cr else "north"
            hi_x = min(room["entrance"]["long_wall_max_x_m"], self.L)
            c = _span_center(0.0, hi_x, w, ent["u"], m)
            if c is None:
                raise LayoutError("entrance does not fit on the long wall")
            y = 0.0 if side == "south" else self.W
            sgn = 1 if side == "south" else -1
            door = {"wall": side, "axis": "x", "center": [c, y], "width": w}
            ys = sorted([y, y + sgn * w])
            swing = Rect(c - w / 2, ys[0], c + w / 2, ys[1])
            yc = sorted([y, y + sgn * max(w, clr)])
            clear = Rect(c - w / 2, yc[0], c + w / 2, yc[1])
            start = (c, y + sgn * 0.4)
        door.update(height=room["entrance"]["height_m"], hinge=ent["hinge"], open_angle_deg=ent["open_angle_deg"],
                    swing=swing.as_list(), placed_on=wall)
        self.keepouts += [("entrance_swing", swing), ("entrance_clear", clear)]
        self.out["entrance"] = door
        self.out["walk_start"] = list(start)
        self._entrance_marker(door)

    def _entrance_marker(self, door):
        """Where the patient first stands still just inside the entrance, facing into the room (local -Y)."""
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
        """Smallest x on a long wall that is free of the changing room and an entrance door."""
        lo = 0.0
        if (wall_name == "north") == (self.spec["changing_room_corner"] == "north"):
            lo = self.changing_block.x1
        ent = self.out["entrance"]
        if ent["wall"] == wall_name:
            lo = max(lo, ent["center"][0] + ent["width"] / 2 + 0.05)
        return lo

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

    # --- wall segments ---------------------------------------------------------------------------
    def exam_segments(self):
        L, W, b = self.L, self.W, self.changing_block
        north = self.spec["changing_room_corner"] == "north"
        segs = [WallSegment("south", "x", 0.0, 0.0, L, (0, 1)), WallSegment("north", "x", W, 0.0, L, (0, -1)),
                WallSegment("west", "y", 0.0, 0.0, W, (1, 0)), WallSegment("east", "y", L, 0.0, W, (-1, 0)),
                WallSegment("changing_east", "y", b.x1, b.y0, b.y1, (1, 0))]
        segs.append(WallSegment("changing_inner", "x", b.y0, 0.0, b.x1, (0, -1)) if north else
                    WallSegment("changing_inner", "x", b.y1, 0.0, b.x1, (0, 1)))
        return segs

    # --- walk check ------------------------------------------------------------------------------
    def walk_ok(self, extra=()) -> bool:
        walk = self.cfg["room"]["walk"]
        g, r = walk["grid_m"], walk["agent_radius_m"]
        xs = np.arange(g / 2, self.L, g)
        ys = np.arange(g / 2, self.W, g)
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        blocked = (X < r) | (Y < r) | (X > self.L - r) | (Y > self.W - r)
        for _, rect in self.obstacles + list(extra):
            dx = np.maximum(np.maximum(rect.x0 - X, 0.0), X - rect.x1)
            dy = np.maximum(np.maximum(rect.y0 - Y, 0.0), Y - rect.y1)
            blocked |= dx * dx + dy * dy < r * r

        def cell(p):
            return (min(max(int(p[0] / g), 0), len(xs) - 1), min(max(int(p[1] / g), 0), len(ys) - 1))

        start = cell(self.out["walk_start"])
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
        cr = self.out["changing_room"]
        goals = [cr["point_inside"], cr["point_outside"], self.out["marker"]["stand_point"]]
        for gx, gy in goals:
            near = (X - gx) ** 2 + (Y - gy) ** 2 <= 0.35 ** 2
            if not (seen & near).any():
                return False
        return True

    # --- changing room furniture ------------------------------------------------------------------
    def changing_furniture(self, rng):
        cr, room = self.spec["changing_room"], self.cfg["room"]["changing_room"]
        it, north = self.changing_interior, self.spec["changing_room_corner"] == "north"
        segs = {"west": WallSegment("west", "y", 0.0, it.y0, it.y1, (1, 0)),
                "east": WallSegment("east", "y", it.x1, it.y0, it.y1, (-1, 0)),
                "outer": (WallSegment("outer", "x", it.y1, 0.0, it.x1, (0, -1)) if north else
                          WallSegment("outer", "x", it.y0, 0.0, it.x1, (0, 1))),
                "inner": (WallSegment("inner", "x", it.y0, 0.0, it.x1, (0, 1)) if north else
                          WallSegment("inner", "x", it.y1, 0.0, it.x1, (0, -1)))}
        door_wall = self.spec["changing_door_wall"]
        candidates = [n for n in ("west", "outer", "inner", "east") if n != door_wall]
        bench = None
        depth = room["bench_depth_m"]
        for name in candidates:
            seg = segs[name]
            length = seg.hi - seg.lo - 0.04
            while length >= 0.6 and bench is None:
                for along in np.linspace(seg.lo + length / 2 + 0.02, seg.hi - length / 2 - 0.02, 5):
                    rect = seg.place(float(along), length, depth)
                    if rect.inside(it) and not rect.overlaps(self.changing_swing):
                        bench = {"wall": name, "rect": rect.as_list(), "yaw_deg": seg.yaw, "length_m": length,
                                 "depth_m": depth, "height_m": room["bench_height_m"], "color": cr["bench_color"]}
                        break
                length -= 0.1
            if bench:
                break
        if bench is None:
            raise LayoutError("no space for the bench in the changing room")
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
                if not rect.overlaps(self.changing_swing.inflate(0.05)) and not rect.overlaps(bench_rect.inflate(0.05)) \
                        and self.walk_ok(extra=[("cr_chair", rect)]):
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
        x_lo, x_hi = self.changing_block.x1, self.L
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
    if not lay.walk_ok():
        raise LayoutError("walk path entrance -> changing room -> floor marker is blocked by the equipment")
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
