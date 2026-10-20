"""Placement of the room on the Isaac Sim stage: a rotate-Z + translate on the root prim so that the entrance
door faces the viewer (export.placement.door_facing) and the chosen origin sits at (0, 0, 0).

Geometry is authored in room coordinates (origin at the interior floor corner of the entrance end); the root
transform maps room -> stage:  p_stage = R(yaw) * p_room + t.
"""

import math

FACING = {"-Y": (0.0, -1.0), "+Y": (0.0, 1.0), "-X": (-1.0, 0.0), "+X": (1.0, 0.0)}
WALL_OUTWARD = {"west": (-1.0, 0.0), "east": (1.0, 0.0), "south": (0.0, -1.0), "north": (0.0, 1.0)}


def entrance_outward(spec: dict):
    """Outward normal (room frame) of the entrance wall: the direction from the room into the corridor."""
    return WALL_OUTWARD[spec["layout"]["entrance"]["wall"]]


def _rot(v, yaw_deg):
    a = math.radians(yaw_deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


class Placement:
    def __init__(self, spec: dict, cfg: dict):
        pcfg = cfg["export"].get("placement") or {}
        self.door_facing = pcfg.get("door_facing", "-Y")
        self.origin_mode = pcfg.get("origin", "center")
        out = entrance_outward(spec)
        target = FACING[self.door_facing]
        yaw = math.degrees(math.atan2(target[1], target[0]) - math.atan2(out[1], out[0]))
        self.yaw_deg = round((yaw + 180.0) % 360.0 - 180.0, 6)
        L, W = spec["footprint_m"]
        if self.origin_mode == "center":
            origin = (L / 2, W / 2)
        elif self.origin_mode == "entrance_door":
            origin = tuple(spec["layout"]["entrance"]["center"])
        else:
            origin = (0.0, 0.0)
        ox, oy = _rot(origin, self.yaw_deg)
        self.translate = (-ox, -oy, 0.0)
        self.origin_room = origin

    def to_stage(self, p):
        x, y = _rot((p[0], p[1]), self.yaw_deg)
        z = p[2] if len(p) > 2 else 0.0
        return [round(x + self.translate[0], 5), round(y + self.translate[1], 5), round(z, 5)]

    def dir_to_stage(self, v):
        x, y = _rot((v[0], v[1]), self.yaw_deg)
        return [round(x, 6), round(y, 6), round(v[2] if len(v) > 2 else 0.0, 6)]

    def as_dict(self):
        return {"door_facing": self.door_facing, "origin": self.origin_mode, "origin_room_m": list(self.origin_room),
                "yaw_deg": self.yaw_deg, "translate_m": list(self.translate),
                "note": "p_stage = rotateZ(yaw) * p_room + translate (applied on the root prim)"}
