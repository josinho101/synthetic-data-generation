"""Per-room metadata JSON (<id>.json): every sampled value, the layout, world anchors, prim paths, photometry."""

import json
from datetime import datetime, timezone
from pathlib import Path

from ..placement import Placement


def write_room_metadata(path, spec: dict, build: dict, run_id: str, generator_version: str) -> dict:
    lay = spec["layout"]
    eq = lay["equipment"]
    place = Placement(spec, _cfg_for_placement(build))
    cameras = [dict(c, prim=build["prims"].get("cameras", {}).get(c["name"]), position_stage=place.to_stage(c["position"]),
                    target_stage=place.to_stage(c["target"])) for c in spec.get("cameras", [])]
    stand = lay["marker"]["stand_point"] + [0.0]
    em = lay.get("entrance_marker")
    meta = {
        "id": spec["id"], "run_id": run_id, "generator_version": generator_version,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": spec["seed"], "attempt": spec["attempt"], "layout_rejections": spec.get("layout_rejections", []),
        "usd": Path(build["usd"]).name, "units": {"meters_per_unit": 1.0, "up_axis": "Z"},
        "coordinate_frame": "room frame: origin = interior floor corner at the entrance end; x along the room, "
                            "y across, z up. *_stage values are on the Isaac stage (after the root placement)",
        "placement": build.get("placement"),
        "room": {"footprint_m": spec["footprint_m"], "ceiling_height_m": spec["ceiling_height_m"],
                 "wall_finish": spec["walls"], "floor": spec["floor"], "door_color": spec["door_color"]},
        "lighting": {"cct_class": spec["cct_class"], "cct_k": spec["cct_k"], "panel_size": spec["panel_size"],
                     "panels": lay["panels"], "photometry": build["photometry"]},
        "equipment": {"detector_side": spec["detector_side"], "finish": spec["finish"], **eq},
        "anchors": {
            "patient_stand": {"position": lay["marker"]["stand_point"] + [0.0], "yaw_deg": lay["marker"]["yaw_deg"],
                              "faces": "local -Y towards the detector", "prim": build["prims"]["markers"]["patient_stand"]},
            "entrance_stand": em and {"position": em["stand_point"] + [0.0], "yaw_deg": em["yaw_deg"],
                                      "faces": "local -Y into the room",
                                      "prim": build["prims"]["markers"].get("entrance_stand")},
            "detector_center": eq["detector"]["center"], "detector_normal": eq["detector"]["normal"],
            "focal_spot": eq["focal_spot"], "beam_axis": eq["beam_axis"], "sid_m": eq["sid_m"],
            "entrance_door": lay["entrance"]["center"], "changing_door": lay["changing_room"]["door"]["center"],
            "changing_room_inside": lay["changing_room"]["point_inside"],
            "stage": {"patient_stand": place.to_stage(stand),
                      "patient_yaw_deg": round((lay["marker"]["yaw_deg"] + place.yaw_deg + 180) % 360 - 180, 4),
                      "detector_center": place.to_stage(eq["detector"]["center"]),
                      "detector_normal": place.dir_to_stage(eq["detector"]["normal"]),
                      "focal_spot": place.to_stage(eq["focal_spot"]), "beam_axis": place.dir_to_stage(eq["beam_axis"]),
                      "entrance_door": place.to_stage(lay["entrance"]["center"] + [0.0]),
                      "entrance_stand": em and place.to_stage(em["stand_point"] + [0.0]),
                      "entrance_yaw_deg": em and round((em["yaw_deg"] + place.yaw_deg + 180) % 360 - 180, 4),
                      "changing_door": place.to_stage(lay["changing_room"]["door"]["center"] + [0.0])},
        },
        "cameras": cameras,
        "camera_coverage": spec.get("camera_coverage", {}),
        "changing_room": lay["changing_room"],
        "entrance": lay["entrance"],
        "patient_support": lay.get("patient_support"),
        "props": lay.get("props", []), "props_requested": [p["name"] for p in spec.get("props_requested", [])],
        "props_dropped": lay.get("dropped", []), "cable_runs": lay.get("cable_runs", []),
        "prims": build["prims"], "semantic_labels": build["semantic_labels"], "textures": build["textures"],
        "layout_notes": lay.get("notes", []), "warnings": lay.get("warnings", []),
    }
    Path(path).write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return meta


def _cfg_for_placement(build: dict) -> dict:
    p = build.get("placement") or {}
    return {"export": {"placement": {"door_facing": p.get("door_facing", "-Y"), "origin": p.get("origin", "center")}}}
