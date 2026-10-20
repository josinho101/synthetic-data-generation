"""2-D floor geometry: axis-aligned rectangles and wall segments (meters, room coordinates)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @staticmethod
    def centered(cx, cy, sx, sy) -> "Rect":
        return Rect(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2)

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2

    @property
    def sx(self):
        return self.x1 - self.x0

    @property
    def sy(self):
        return self.y1 - self.y0

    def inflate(self, d: float) -> "Rect":
        return Rect(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def overlaps(self, other: "Rect", eps: float = 1e-9) -> bool:
        return (self.x0 < other.x1 - eps and other.x0 < self.x1 - eps and
                self.y0 < other.y1 - eps and other.y0 < self.y1 - eps)

    def inside(self, other: "Rect", eps: float = 1e-9) -> bool:
        return (self.x0 >= other.x0 - eps and self.x1 <= other.x1 + eps and
                self.y0 >= other.y0 - eps and self.y1 <= other.y1 + eps)

    def contains(self, x, y) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def distance_to(self, x, y) -> float:
        dx = max(self.x0 - x, 0.0, x - self.x1)
        dy = max(self.y0 - y, 0.0, y - self.y1)
        return (dx * dx + dy * dy) ** 0.5

    def as_list(self):
        return [round(self.x0, 4), round(self.y0, 4), round(self.x1, 4), round(self.y1, 4)]

    @staticmethod
    def from_list(values) -> "Rect":
        return Rect(*values)


# Inward normal of each wall -> yaw (deg) that turns an object's local +Y (its front) into that normal.
WALL_YAW = {"south": 0.0, "north": 180.0, "west": -90.0, "east": 90.0}


def footprint_for_yaw(sx: float, sy: float, yaw: float):
    """World-axis footprint size of an object with local size (sx, sy) rotated by a multiple of 90 deg."""
    return (sy, sx) if round(yaw / 90.0) % 2 else (sx, sy)


@dataclass(frozen=True)
class WallSegment:
    """A straight piece of wall face that objects can stand against."""
    name: str
    axis: str        # "x": the face runs along x (constant y); "y": runs along y (constant x)
    coord: float     # the constant coordinate of the face
    lo: float        # extent along the axis
    hi: float
    normal: tuple    # inward normal (unit, axis-aligned)

    @property
    def yaw(self) -> float:
        return {(0, 1): 0.0, (0, -1): 180.0, (1, 0): -90.0, (-1, 0): 90.0}[tuple(int(v) for v in self.normal)]

    def place(self, along: float, sx: float, sy: float) -> Rect:
        """Footprint of an object (local size sx, sy) flush against this face, centred at `along`."""
        wx, wy = footprint_for_yaw(sx, sy, self.yaw)
        if self.axis == "x":
            y0 = self.coord if self.normal[1] > 0 else self.coord - wy
            return Rect(along - wx / 2, y0, along + wx / 2, y0 + wy)
        x0 = self.coord if self.normal[0] > 0 else self.coord - wx
        return Rect(x0, along - wy / 2, x0 + wx, along + wy / 2)
