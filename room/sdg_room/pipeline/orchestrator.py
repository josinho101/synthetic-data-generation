"""Pipeline orchestration: preflight -> sample (spec + layout) -> build (parallel processes) -> validate -> report."""

import json
import logging
import shutil
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from .. import __version__
from ..config.schema import footprint_m
from ..logging_setup import setup_run_logging, setup_worker_logging
from ..metadata import report
from ..metadata.writer import write_room_metadata
from ..progress import Progress, fmt_duration, print_distribution_table
from ..run_context import create_run, open_run, snapshot_config
from ..sampling.manifest import build_specs, read_manifest, write_manifest
from .validate import validate_usd

_LOG = logging.getLogger("sdg_room.pipeline")


def preflight(cfg: dict) -> list:
    """Environment checks; returns a list of problems (empty = ok)."""
    problems = []
    need = tuple(int(v) for v in str(cfg["export"].get("min_python", "3.10")).split("."))
    if sys.version_info[:len(need)] < need:
        problems.append(f"Python {sys.version.split()[0]} < {cfg['export']['min_python']}")
    for module in ("pxr", "numpy", "PIL", "yaml"):
        try:
            __import__(module)
        except ImportError:
            problems.append(f"Python package '{module}' missing (pip install -r requirements.txt)")
    root = Path(cfg["export"]["output_root"])
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("ok")
        probe.unlink()
        free_mb = shutil.disk_usage(root).free / 1e6
        need_mb = cfg["variations"]["count"] * cfg["export"].get("est_mb_per_room", 15)
        if free_mb < need_mb:
            problems.append(f"only {free_mb:.0f} MB free in {root} (~{need_mb:.0f} MB needed)")
    except OSError as exc:
        problems.append(f"output_root {root} not writable: {exc}")
    for part in ("wall_stand", "tube_stand"):
        asset = cfg["equipment"][part].get("asset")
        if asset and not Path(asset).exists():
            problems.append(f"equipment.{part}.asset not found: {asset}")
    return problems


def build_one(cfg: dict, spec: dict, room_dir: str, log_path: str, run_id: str) -> dict:
    """Worker process: USD + plan PNG + metadata + validation for one room."""
    from ..preview.plan_png import render_plan
    from ..usd.build import build_room_usd

    log = setup_worker_logging(log_path, cfg["logging"].get("worker_level", "INFO"), cfg["logging"].get("worker_format"))
    started = time.monotonic()
    room_dir = Path(room_dir)
    try:
        log.info(f"{spec['id']}: build start (seed {spec['seed']}, attempt {spec['attempt']})")
        for note in spec["layout"].get("notes", []):
            log.info(f"{spec['id']}: layout note: {note}")
        build = build_room_usd(cfg, spec, room_dir, __version__)
        render_plan(spec, room_dir / f"{spec['id']}_plan.png", cfg["export"]["preview"].get("plan_px_per_m", 160),
                    cfg["room"]["wall_thickness_m"])
        check = validate_usd(build["usd"], spec["footprint_m"], spec["ceiling_height_m"], cfg["room"]["wall_thickness_m"],
                             cfg["export"].get("semantics", True), cfg["export"]["physics"]["colliders"],
                             spec.get("cameras"))
        meta = write_room_metadata(room_dir / f"{spec['id']}.json", spec, build, run_id, __version__)
        meta["validation"] = check
        (room_dir / f"{spec['id']}.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
        warnings = spec["layout"].get("warnings", []) + check["warnings"]
        status = "failed" if check["status"] == "failed" else ("warn" if warnings else "ok")
        result = {"status": status, "usd": build["usd"], "warnings": warnings, "validation": check,
                  "lux_estimated": build["photometry"]["exam"]["estimated_lux_mean"]}
        if status == "failed":
            result["error"] = f"USD validation: {check['errors'][:2]}"
        log.info(f"{spec['id']}: {status} validation={check['status']} meshes={check['meshes']} lights={check['lights']}")
        for err in check["errors"]:
            log.error(f"{spec['id']}: {err}")
    except Exception as exc:  # noqa: BLE001 - one bad room must not stop the run
        log.error(f"{spec['id']}: build failed: {exc}\n{traceback.format_exc()}")
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    result["duration_s"] = round(time.monotonic() - started, 2)
    result["log"] = log_path
    return result


def _results_path(ctx) -> Path:
    return ctx.run_dir / "results.json"


def _load_results(ctx) -> dict:
    path = _results_path(ctx)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_results(ctx, results: dict) -> None:
    _results_path(ctx).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def run_pipeline(cfg: dict, config_dir, run_dir=None, resume=False, only=None, skip_preflight=False) -> int:
    started = time.monotonic()
    export = cfg["export"]
    ctx = open_run(run_dir) if run_dir else create_run(export["output_root"], export.get("run_dir_format", "run-%Y%m%d-%H%M%S"))
    central = setup_run_logging(cfg["logging"], ctx.run_dir, ctx.run_id)
    _LOG.info(f"[run] {ctx.run_id}  dir={ctx.run_dir}  (central log {central})")
    timings = {}

    if not skip_preflight:
        problems = preflight(cfg)
        (ctx.run_dir / "preflight.json").write_text(json.dumps({"problems": problems}, indent=2), encoding="utf-8")
        for p in problems:
            _LOG.error(f"[preflight] FAIL {p}")
        if problems:
            return 2
        _LOG.info("[preflight] PASSED")
    snapshot_config(ctx, cfg, config_dir)

    t = time.monotonic()
    if run_dir:
        specs = read_manifest(ctx.manifest_path)
        _LOG.info(f"[sample] reusing manifest with {len(specs)} rooms")
    else:
        L, W = footprint_m(cfg["room"])
        _LOG.info(f"[sample] {cfg['variations']['count']} rooms, seed {cfg['variations']['seed']}, footprint "
                  f"{L:.3f} x {W:.3f} m")
        specs = build_specs(cfg)
        write_manifest(ctx.manifest_path, specs, {"run_id": ctx.run_id, "generator_version": __version__,
                                                  "seed": cfg["variations"]["seed"]})
        for key in report.CATEGORICAL:
            counts = {}
            for s in specs:
                counts[s[key]] = counts.get(s[key], 0) + 1
            print_distribution_table(key, cfg["variations"][key], counts, len(specs))
    timings["sample"] = round(time.monotonic() - t, 2)

    results = _load_results(ctx)
    todo = specs
    if only:
        todo = [s for s in specs if s["id"] in set(only)]
        missing = set(only) - {s["id"] for s in todo}
        if missing:
            _LOG.error(f"[build] unknown room ids: {sorted(missing)}")
            return 2
    elif resume:
        todo = [s for s in specs if results.get(s["id"], {}).get("status") not in ("ok", "warn")
                or not (ctx.room_dir(s["id"]) / f"{s['id']}.json").exists()]
    _LOG.info(f"[build] {len(todo)} rooms with {export['workers']} worker(s)")

    t = time.monotonic()
    progress = Progress(len(todo))
    attempts = int(export.get("retries", 0)) + 1
    with ProcessPoolExecutor(max_workers=int(export["workers"])) as pool:
        pending = {pool.submit(build_one, cfg, s, str(ctx.room_dir(s["id"])), str(ctx.room_log(s["id"])), ctx.run_id):
                   (s, 1) for s in todo}
        while pending:
            for fut in as_completed(list(pending)):
                spec, attempt = pending.pop(fut)
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001 - worker crashed
                    result = {"status": "failed", "error": f"worker crashed: {exc}"}
                if result["status"] == "failed" and attempt < attempts:
                    _LOG.warning(f"{spec['id']}: attempt {attempt}/{attempts} failed: {result.get('error')}")
                    pending[pool.submit(build_one, cfg, spec, str(ctx.room_dir(spec["id"])),
                                        str(ctx.room_log(spec["id"])), ctx.run_id)] = (spec, attempt + 1)
                    continue
                results[spec["id"]] = result
                _save_results(ctx, results)
                progress.finish_item(spec, result)
                break
    timings["build"] = round(time.monotonic() - t, 2)

    t = time.monotonic()
    report.write_rooms_csv(ctx.run_dir / "rooms.csv", specs, results)
    report.contact_sheet(ctx.run_dir, [s["id"] for s in specs], ctx.run_dir / "contact_sheet.png",
                         export["preview"].get("contact_sheet_columns", 4))
    timings["report"] = round(time.monotonic() - t, 2)
    timings["total"] = round(time.monotonic() - started, 2)
    summary = report.write_summary(ctx.run_dir / "summary.json", cfg, specs, results, timings)
    _LOG.info(f"[done] {summary['status']} in {fmt_duration(timings['total'])} -> {ctx.run_dir}")
    if summary["failed"]:
        _LOG.error(f"[done] failed rooms: {summary['failed']} (see logs/errors.log)")
    return 1 if summary["failed"] else 0
