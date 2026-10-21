"""Orchestrate a run: resolve inputs -> plan visits -> SD folders -> Isaac Sim -> summary."""

import json
import shutil
import logging
import tempfile
import time
from pathlib import Path

from . import sd as sdmod
from .capture import cameras_for_sd, capture_disk_estimate, choose_group_options, every_n_frames
from .config import ConfigError
from .launcher import isaac_python, isaac_version, run_isaac
from .paths import COMPOSE_SCENE, DEFAULT_HUMANS_ROOT, DEFAULT_OUTPUT_ROOT, DEFAULT_ROOMS_ROOT
from .sources import resolve_run, select_items
from .visit import chest_height, describe, load_json, plan_visit

log = logging.getLogger(__name__)


def build_jobs(cfg: dict) -> dict:
    """Resolve humans and rooms and plan every visit. Raises ConfigError on bad inputs."""
    run = cfg["run"]
    humans_run = resolve_run(run["humans"].get("root"), "humans", DEFAULT_HUMANS_ROOT)
    rooms_run = resolve_run(run["rooms"].get("root"), "rooms", DEFAULT_ROOMS_ROOT)
    humans = select_items(humans_run, "humans", run["humans"].get("count"), run["humans"].get("ids"))
    rooms = select_items(rooms_run, "rooms", run["rooms"].get("count"), run["rooms"].get("ids"))
    log.info("Humans: %s from %s", ", ".join(h["id"] for h in humans), humans_run)
    log.info("Rooms:  %s from %s", ", ".join(r["id"] for r in rooms), rooms_run)

    room_meta = {r["id"]: load_json(r["json"]) for r in rooms}
    plans = {}
    for room in rooms:
        for exam, projections in run["exams"].items():
            plans[(room["id"], exam)] = plan_visit(room_meta[room["id"]], projections, cfg)

    subjects = []
    for human in humans:
        meta = load_json(human["json"])
        height = chest_height(meta)
        if height is None:
            raise ConfigError(f"human {human['id']}: no T7 / chest landmarks in {human['json']}")
        garments = [i.get("asset") for i in (meta.get("clothing") or {}).get("items", []) if i.get("asset")]
        subjects.append(dict(human, chest_height_m=round(height, 4), height_cm=(meta.get("body") or {}).get("height_cm"),
                             clothing=garments))
    return {"humans_run": str(humans_run), "rooms_run": str(rooms_run), "humans": subjects, "rooms": rooms, "plans": plans}


def _visits(cfg, jobs, sd_names, output_root):
    multi_room = len(jobs["rooms"]) > 1
    visits = []
    for human, sd_name in zip(jobs["humans"], sd_names):
        sd_dir = output_root / sd_name
        for exam, projections in cfg["run"]["exams"].items():
            for room in jobs["rooms"]:
                timeline = sdmod.timeline_path(sd_dir, exam, room["id"], multi_room)
                visits.append({
                    "sd": sd_name, "sd_dir": str(sd_dir), "exam": exam, "projections": projections,
                    "human": human, "room": room, "timeline": str(timeline),
                    "steps": jobs["plans"][(room["id"], exam)],
                    "header": {"sd": sd_name, "human": f"{human['id']} ({Path(human['run']).name})",
                               "room": f"{room['id']} ({Path(room['run']).name})", "exam": exam,
                               "projections": ", ".join(projections), "started": sdmod.now_iso()},
                })
    return visits


def run_pipeline(cfg: dict, dry_run: bool = False, verbose: bool = False) -> int:
    t0 = time.time()
    try:
        jobs = build_jobs(cfg)
        if not dry_run:
            isaac_python(cfg["isaac"])
    except ConfigError as exc:
        log.error("[ERROR] %s", exc)
        return 2

    for (room_id, exam), steps in jobs["plans"].items():
        log.info("Visit plan %s / %s (%d steps):", room_id, exam, len(steps))
        for line in describe(steps):
            log.info(line)
    if dry_run:
        log.info("Dry run: %d human(s) x %d room(s) x %d exam(s); Isaac Sim not started",
                 len(jobs["humans"]), len(jobs["rooms"]), len(cfg["run"]["exams"]))
        return 0

    output_root = Path(cfg["run"].get("output_root") or DEFAULT_OUTPUT_ROOT)
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = sdmod.create_run_dir(output_root, cfg["run"].get("run_dir_format", "run-%Y%m%d-%H%M%S"))
    log.info("Output: %s", run_dir)
    sd_names = sdmod.next_sd_numbers(run_dir, len(jobs["humans"]), cfg["run"].get("sd_id_format", "SD.{:05d}"))
    visits = _visits(cfg, jobs, sd_names, run_dir)
    cap = cfg["capture"]
    capture_by_sd = {}
    if cap.get("enabled"):
        picks = choose_group_options(output_root, cap.get("groups") or {}, len(sd_names))
        for sd_name, pick in zip(sd_names, picks):
            capture_by_sd[sd_name] = {"groups": pick, "cameras": cameras_for_sd(cap, pick)}
            log.info("%s records %s", sd_name, ", ".join(c["name"] for c in capture_by_sd[sd_name]["cameras"]))
        for v in visits:
            v["capture"] = dict(capture_by_sd[v["sd"]], dir=str(Path(v["timeline"]).parent))
        need, free = capture_disk_estimate(cfg, visits), shutil.disk_usage(output_root).free
        log.info("Capture: about %.1f GB for %d visit(s), %.1f GB free on %s", need / 1e9, len(visits), free / 1e9, output_root)
        if need * 1.15 > free:
            log.error("[ERROR] not enough disk space for the capture: need about %.1f GB, %.1f GB free. Lower "
                      "capture.fps, use fewer cameras / streams, or free space", need / 1e9, free / 1e9)
            return 2
    for human, sd_name in zip(jobs["humans"], sd_names):
        sdmod.write_json(run_dir / sd_name / "sd_info.json", {
            "sd": sd_name, "run": run_dir.name, "status": "pending", "created": sdmod.now_iso(),
            "human": {k: human[k] for k in ("id", "usd", "json", "run", "height_cm", "chest_height_m")},
            "rooms": [{k: r[k] for k in ("id", "usd", "run")} for r in jobs["rooms"]],
            "exams": cfg["run"]["exams"], "isaac_version": isaac_version(cfg["isaac"]),
            "capture": ({"groups": capture_by_sd[sd_name]["groups"],
                         "cameras": [c["name"] for c in capture_by_sd[sd_name]["cameras"]],
                         "fps": cfg["isaac"].get("fps", 30) / every_n_frames(cfg),
                         "sim_fps": cfg["isaac"].get("fps", 30), "every_n_frames": every_n_frames(cfg)}
                        if sd_name in capture_by_sd else None),
            "visits": {f"{v['exam']}/{v['room']['id']}": {"status": "pending", "timeline": v["timeline"]}
                       for v in visits if v["sd"] == sd_name},
        })
        log.info("%s <- human %s", sd_name, human["id"])

    job = {"isaac": cfg["isaac"], "sequence": cfg["sequence"], "retarget_tags": cfg["retarget_mpfb"]["tags"],
           "root_joint_name": cfg["retarget_mpfb"].get("root_joint_name", "SkelOrigin"),
           "up_axis": cfg["retarget_mpfb"].get("up_axis", "Z"),
           "forward_axis": cfg["retarget_mpfb"].get("forward_axis", "MINUS Y"),
           "compose_scene": str(COMPOSE_SCENE), "visits": visits,
           "capture": cfg["capture"], "arm_poses": cfg["poses"]["arm_poses"], "timing": cfg["poses"].get("timing") or {},
           "debug_hands": bool(cfg["isaac"].get("debug_hands", False))}
    with tempfile.NamedTemporaryFile("w", prefix="xray_job_", suffix=".json", delete=False) as handle:
        json.dump(job, handle, indent=1)
        job_file = Path(handle.name)
    try:
        code = run_isaac(job_file, cfg["isaac"], verbose=verbose)
    finally:
        job_file.unlink(missing_ok=True)

    failed = 0
    for sd_name in sd_names:
        info_path = run_dir / sd_name / "sd_info.json"
        info = json.loads(info_path.read_text())
        states = [v["status"] for v in info["visits"].values()]
        info["status"] = "ok" if states and all(s == "ok" for s in states) else "failed"
        failed += info["status"] != "ok"
        sdmod.write_json(info_path, info)
        log.info("%s: %s (%s)", sd_name, info["status"], ", ".join(f"{k} {v['status']}" for k, v in info["visits"].items()))
    log.info("Done in %.0f s: %d SD ok, %d failed -> %s", time.time() - t0, len(sd_names) - failed, failed, run_dir)
    if code != 0:
        log.error("[ERROR] Isaac Sim ended with exit code %s", code)
        return 1
    return 1 if failed else 0
