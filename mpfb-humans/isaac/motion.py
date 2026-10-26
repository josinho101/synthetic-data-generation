"""Procedural motion for MPFB humans: idle -> walk -> idle -> jump -> turn + walk back -> turn -> idle.

Pure Python (no pxr). pose_at(t) returns joint rotations as (skeleton-space axis, degrees)
pairs and the root motion. Conventions (skeleton space = human rest pose): front = -Y,
left = +X, up = +Z. A rotation of +deg about X swings a hanging limb backwards and bends
an upright segment forwards.
"""

import math

DEFAULTS = {
    "fps": 30, "idle_s": 2.0, "pause_s": 1.5, "walk_distance_m": 3.0, "walk_speed_mps": 1.15,
    "gait_cycle_s": 1.1, "turn_s": 1.2, "jump_height_m": 0.22, "arm_lower_deg": 42.0,
}


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def segments(cfg: dict) -> list:
    """[(name, start_s, duration_s), ...] of the whole clip."""
    walk = cfg["walk_distance_m"] / cfg["walk_speed_mps"]
    order = [("idle", cfg["idle_s"]), ("walk", walk), ("idle", cfg["pause_s"]), ("jump", 1.9),
             ("idle", 1.0), ("turn", cfg["turn_s"]), ("walk", walk), ("turn", cfg["turn_s"]), ("idle", cfg["idle_s"])]
    out, start = [], 0.0
    for name, duration in order:
        out.append((name, start, duration))
        start += duration
    return out


def duration(cfg: dict) -> float:
    name, start, length = segments(cfg)[-1]
    return start + length


def _base(cfg, rot):
    """Arms down from MPFB's A-pose, relaxed elbows (applied in every phase)."""
    lower = cfg["arm_lower_deg"]
    back = cfg.get("arm_back_deg", 9.0)          # MPFB A-pose arms point slightly forward
    rot["upperarm01_L"] = [("Y", lower), ("X", back)]
    rot["upperarm01_R"] = [("Y", -lower), ("X", back)]
    rot["lowerarm01_L"] = [("X", -12.0)]
    rot["lowerarm01_R"] = [("X", -12.0)]


def _add(rot, joint, axis, deg):
    rot.setdefault(joint, []).append((axis, deg))


def _idle(cfg, rot, t):
    breath = math.sin(2 * math.pi * t / 4.0)
    _add(rot, "spine03", "X", 1.2 * breath)
    _add(rot, "neck01", "X", -0.8 * breath)
    sway = math.sin(2 * math.pi * t / 6.0)
    _add(rot, "upperarm01_L", "X", 2.0 * sway)
    _add(rot, "upperarm01_R", "X", -2.0 * sway)


def _walk(cfg, rot, t, length):
    ramp = smoothstep(t / 0.5) * smoothstep((length - t) / 0.5)
    phi = 2 * math.pi * t / cfg["gait_cycle_s"]
    for side, offset in (("L", 0.0), ("R", math.pi)):
        p = phi + offset
        _add(rot, f"upperleg01_{side}", "X", -24.0 * math.sin(p) * ramp)
        _add(rot, f"lowerleg01_{side}", "X", (4.0 + 42.0 * max(0.0, math.cos(p + 0.6)) ** 2) * ramp)
        _add(rot, f"foot_{side}", "X", -8.0 * math.sin(p + 1.0) * ramp)
        _add(rot, f"upperarm01_{side}", "X", 16.0 * math.sin(p) * ramp)
        _add(rot, f"lowerarm01_{side}", "X", -10.0 * max(0.0, -math.sin(p)) * ramp)
    _add(rot, "spine03", "Z", 4.0 * math.sin(phi) * ramp)
    _add(rot, "spine05", "X", 3.0 * ramp)


def _jump(cfg, rot, t):
    """crouch (0-0.5) -> push (0.5-0.65) -> air (0.65-1.1) -> land (1.1-1.4) -> recover (1.4-1.9)."""
    if t < 0.5:
        c = smoothstep(t / 0.5)
    elif t < 0.65:
        c = 1.0 - smoothstep((t - 0.5) / 0.15)
    elif t < 1.1:
        c = 0.25 * math.sin(math.pi * (t - 0.65) / 0.45)
    elif t < 1.4:
        c = 0.7 * math.sin(math.pi * 0.5 * (t - 1.1) / 0.3)
    else:
        c = 0.7 * (1.0 - smoothstep((t - 1.4) / 0.5))
    arms = 45.0 * c if t < 0.5 else (-70.0 * math.sin(math.pi * min(1.0, (t - 0.5) / 0.6)) if t < 1.1 else 20.0 * c)
    for side in ("L", "R"):
        _add(rot, f"upperleg01_{side}", "X", -50.0 * c)
        _add(rot, f"lowerleg01_{side}", "X", 85.0 * c)
        _add(rot, f"foot_{side}", "X", -30.0 * c)
        _add(rot, f"upperarm01_{side}", "X", arms)
    _add(rot, "spine05", "X", 22.0 * c)
    _add(rot, "neck01", "X", -12.0 * c)


def jump_lift(cfg, t) -> float:
    if 0.65 <= t <= 1.1:
        u = (t - 0.65) / 0.45
        return 4.0 * cfg["jump_height_m"] * u * (1.0 - u)
    return 0.0


def _turn(cfg, rot, t, length):
    step = math.sin(2 * math.pi * t / (length / 2.0))
    for side, sign in (("L", 1.0), ("R", -1.0)):
        _add(rot, f"upperleg01_{side}", "X", -10.0 * max(0.0, sign * step))
        _add(rot, f"lowerleg01_{side}", "X", 22.0 * max(0.0, sign * step))


def pose_at(t: float, cfg: dict):
    """-> (rotations {joint_leaf: [(axis, deg), ...]}, root {"forward_speed", "yaw_deg", "lift_m"})."""
    rot = {}
    _base(cfg, rot)
    root = {"forward_speed": 0.0, "yaw_deg": 0.0, "lift_m": 0.0}
    turns_done = 0
    for name, start, length in segments(cfg):
        if name == "turn" and t >= start + length:
            turns_done += 1
        if not (start <= t < start + length or (t >= start + length and (name, start) == segments(cfg)[-1][:2])):
            continue
        local = t - start
        if name == "idle":
            _idle(cfg, rot, t)
        elif name == "walk":
            _walk(cfg, rot, local, length)
            root["forward_speed"] = cfg["walk_speed_mps"] * smoothstep(local / 0.5) * smoothstep((length - local) / 0.5)
        elif name == "jump":
            _jump(cfg, rot, local)
            root["lift_m"] = jump_lift(cfg, local)
        elif name == "turn":
            _turn(cfg, rot, local, length)
            root["yaw_deg"] = 180.0 * smoothstep(local / length)
    root["yaw_deg"] += 180.0 * turns_done
    return rot, root
