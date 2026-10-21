"""Plan one exam visit: the ordered steps the patient performs, in Isaac stage coordinates (pure Python).

Step ops (executed by isaac/run_exam.py with the behavior agent API):
  spawn {position, facing}            teleport the patient
  idle  {duration, facing?}           stand (natural idle motion)
  walk  {waypoints, target}           walk along the waypoints (NavMesh path finding between them)
  turn  {facing}                      turn in place
  arms  {pose}                        hands to a pose of poses.arm_poses (or "down")
  fov   {on}                          collimator FOV light on / off
Each step has `say` (timeline text when it starts) and optionally `done` (timeline text when it ends).
"""

import json
import math

from .config import ConfigError

ROUTE_STEPS = ("entrance", "check_in", "connecting_door", "entrance_stand", "patient_stand")


def _rot(v, deg):
    a = math.radians(deg)
    return [v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)]


def _unit(v):
    n = math.hypot(v[0], v[1])
    if n < 1e-9:
        raise ConfigError(f"zero-length direction {v}")
    return [round(v[0] / n, 6), round(v[1] / n, 6), 0.0]


def _yaw_facing(yaw_deg):
    """Facing of a marker whose local -Y is its front, after rotateZ(yaw)."""
    return _unit(_rot([0.0, -1.0], yaw_deg))


def _xyz(p):
    return [round(float(p[0]), 4), round(float(p[1]), 4), 0.0]


def room_anchors(room_meta: dict) -> dict:
    """Stage-frame anchors needed for the visit, validated."""
    stage = (room_meta.get("anchors") or {}).get("stage") or {}
    route = {s["step"]: _xyz(s["position"]) for s in stage.get("patient_route") or []}
    missing = [s for s in ROUTE_STEPS if s not in route]
    if missing or "detector_normal" not in stage or "entrance_door" not in stage:
        raise ConfigError(f"room {room_meta.get('id')}: anchors.stage lacks {missing or 'detector_normal / entrance_door'}"
                          " (regenerate the room with the current room pipeline)")
    entrance = room_meta.get("entrance") or {}
    yaw = (room_meta.get("placement") or {}).get("yaw_deg", 0.0)
    out_normal = _unit(_rot(entrance.get("out_normal") or [0.0, -1.0], yaw))
    detector = _unit([-stage["detector_normal"][0], -stage["detector_normal"][1]])
    return {
        "route": route,
        "entrance_door": _xyz(stage["entrance_door"]),
        "entrance_out": out_normal,
        "entrance_facing": _yaw_facing(stage.get("entrance_yaw_deg", 0.0)) if "entrance_yaw_deg" in stage
        else _unit([route["patient_stand"][0] - route["entrance_stand"][0], route["patient_stand"][1] - route["entrance_stand"][1]]),
        "face_detector": detector,
        "focal_spot": stage.get("focal_spot"),
        "detector_center": stage.get("detector_center"),
    }


def projection_facing(face_detector, facing: str):
    d = face_detector
    return {"detector": d, "left": _unit(_rot(d, 90.0)), "right": _unit(_rot(d, -90.0)), "tube": _unit([-d[0], -d[1]])}[facing]


def chest_height(human_meta: dict):
    t7 = ((human_meta.get("landmarks") or {}).get("T7") or {}).get("rest_position_m")
    if t7:
        return float(t7[2])
    cm = human_meta.get("measurements_cm") or {}
    if "jugular_notch_height_cm" in cm and "xiphoid_height_cm" in cm:
        return (cm["jugular_notch_height_cm"] + cm["xiphoid_height_cm"]) / 200.0
    return None


def plan_visit(room_meta: dict, projections: list, cfg: dict) -> list:
    """Ordered steps of one exam visit (outside -> check-in -> X-ray room -> projections -> back outside)."""
    a = room_anchors(room_meta)
    seq, poses = cfg["sequence"], cfg["poses"]
    idle, timing = seq.get("idle_s") or {}, poses.get("timing") or {}
    r = a["route"]
    start = [round(a["entrance_door"][i] + a["entrance_out"][i] * seq.get("start_outside_m", 1.5), 4) for i in range(2)] + [0.0]
    to_door = _unit([-a["entrance_out"][0], -a["entrance_out"][1]])
    steps = [{"op": "spawn", "position": start, "facing": to_door, "say": "Model loaded outside the room"}]

    def add_idle(key, facing=None, say=None):
        if idle.get(key, 0) > 0:
            steps.append({"op": "idle", "duration": float(idle[key]), "facing": facing, "say": say})

    add_idle("outside", to_door, "Model standing outside the entrance")
    steps.append({"op": "walk", "waypoints": [r["entrance"], r["check_in"]], "target": "check_in",
                  "say": "Model started walking into the check-in room", "done": "Model entered the check-in room"})
    add_idle("check_in", None, "Model standing in the check-in room")
    steps.append({"op": "walk", "waypoints": [r["connecting_door"], r["entrance_stand"]], "target": "entrance_stand",
                  "say": "Model started walking into the X-ray room", "done": "Model standing on the entrance marker"})
    add_idle("entrance_marker", a["entrance_facing"], "Model idle on the entrance marker")
    steps.append({"op": "walk", "waypoints": [r["patient_stand"]], "target": "patient_stand",
                  "say": "Model started walking to the detector marker", "done": "Model reached the detector marker"})
    steps.append({"op": "turn", "facing": a["face_detector"], "duration": float(timing.get("turn_s", 1.6)),
                  "say": "Model turning to face the detector", "done": "Model standing on the detector marker, facing the detector"})
    add_idle("detector_marker", a["face_detector"], "Model idle on the detector marker")

    for k, name in enumerate(projections):
        proj = poses["projections"][name]
        label = proj.get("label") or name
        facing = projection_facing(a["face_detector"], proj["facing"])
        turn_words = {"detector": "to face the detector", "left": "left", "right": "right", "tube": "to face the tube"}
        steps.append({"op": "turn", "facing": facing, "duration": float(timing.get("turn_s", 1.6)), "projection": name,
                      "settle": float(timing.get("after_turn_s", 0.0)),
                      "say": f"{name}: Model turning {turn_words[proj['facing']]} ({label})"})
        pose_words = proj["arms"].replace("_", "-")
        hold_s = float(timing.get("settle_s", 0)) + float(timing.get("fov_on_s", 1.0)) + float(timing.get("hold_after_s", 0))
        steps.append({"op": "arms", "pose": proj["arms"], "duration": float(timing.get("arms_up_s", 1.4)), "projection": name,
                      "hold_s": round(hold_s + 0.1, 3),
                      "say": f"{name}: Model moving hands to {pose_words} pose", "done": f"{name}: Model in {pose_words} pose"})
        if timing.get("settle_s", 0) > 0:
            steps.append({"op": "idle", "duration": float(timing["settle_s"]), "facing": facing, "keep_arms": True,
                          "projection": name, "say": None})
        steps.append({"op": "fov", "on": True, "projection": name, "pose_name": proj["arms"], "say": f"{name}: FOV light ON"})
        steps.append({"op": "idle", "duration": float(timing.get("fov_on_s", 1.0)), "facing": facing, "keep_arms": True,
                      "projection": name, "say": None})
        steps.append({"op": "fov", "on": False, "projection": name, "say": f"{name}: FOV light OFF"})
        if timing.get("hold_after_s", 0) > 0:
            steps.append({"op": "idle", "duration": float(timing["hold_after_s"]), "facing": facing, "keep_arms": True,
                          "projection": name, "say": None})
        steps.append({"op": "arms", "pose": "down", "duration": float(timing.get("arms_down_s", 1.2)), "projection": name,
                      "say": f"{name}: Model lowering the arms", "done": f"{name}: Model arms down, {label} done"})
        if k < len(projections) - 1 and timing.get("between_s", 0) > 0:
            steps.append({"op": "idle", "duration": float(timing["between_s"]), "facing": facing, "say": None})

    steps.append({"op": "walk", "waypoints": [r["entrance_stand"]], "target": "entrance_stand",
                  "say": "Model walking back to the door marker", "done": "Model standing on the door marker"})
    add_idle("exit_marker", None, "Model idle on the door marker")
    steps.append({"op": "walk", "waypoints": [r["connecting_door"], r["check_in"], r["entrance"], start], "target": "outside",
                  "say": "Model started leaving the room", "done": "Model left the room"})
    add_idle("end", None, "Model standing outside")
    for i, s in enumerate(steps):
        s["index"] = i + 1
    return steps


def describe(steps: list) -> list:
    """Human-readable lines for --dry-run and logs."""
    lines = []
    for s in steps:
        extra = ""
        if s["op"] == "walk":
            extra = f" -> {s['target']} via {len(s['waypoints'])} point(s)"
        elif s["op"] in ("idle", "turn", "arms") and s.get("duration"):
            extra = f" {s['duration']:.1f}s"
        lines.append(f"  {s['index']:02d} {s['op']:<5}{extra:<34} {s.get('say') or ''}")
    return lines


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
