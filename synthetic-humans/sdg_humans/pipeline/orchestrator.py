"""Pipeline orchestration: preflight -> sample -> build (parallel Blender workers) -> validate -> report."""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import __version__, preflight
from ..logging_setup import setup_run_logging
from ..metadata import report
from ..mpfb_locate import resolve_mpfb_data_dir
from ..progress import Progress, fmt_duration, print_distribution_table
from ..run_context import create_run, open_run, snapshot_config
from ..sampling.face import load_target_catalogue
from ..sampling.manifest import build_specs, read_manifest, write_manifest
from .blender_runner import run_task
from .validate import validate_usd

_LOG = logging.getLogger("sdg_humans.pipeline")


def _results_path(ctx) -> Path:
    return ctx.run_dir / "results.json"


def _load_results(ctx) -> dict:
    path = _results_path(ctx)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_results(ctx, results: dict) -> None:
    _results_path(ctx).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def _build_one(cfg: dict, ctx, spec: dict) -> dict:
    """Build one human in its own Blender process (with retries) and validate the USD."""
    export = cfg["export"]
    log = ctx.human_log(spec["id"])
    args = {"config": cfg, "spec": spec, "human_dir": str(ctx.human_dir(spec["id"])), "run_id": ctx.run_id,
            "generator_version": __version__, "log_level": cfg["logging"].get("worker_level", "INFO"),
            "log_format": cfg["logging"].get("worker_format")}
    attempts = int(export.get("retries", 0)) + 1
    result = {}
    for attempt in range(1, attempts + 1):
        result = run_task(export["blender_bin"], "build", args, log, int(export.get("timeout_s_per_human", 1200)),
                          work_dir=ctx.run_dir / "work" / spec["id"])
        if result.get("status") in ("ok", "warn"):
            break
        _LOG.warning(f"{spec['id']}: attempt {attempt}/{attempts} failed: {result.get('error')}")
    result["log"] = str(log)
    if result.get("status") in ("ok", "warn"):
        human_dir = ctx.human_dir(spec["id"])
        post_cfg = export.get("usd_post") or {}
        if post_cfg.get("enabled", True):
            try:
                result["usd_post"] = _postprocess(result["usd"], human_dir / f"{spec['id']}.json", post_cfg)
            except Exception as exc:  # noqa: BLE001 - reported as a failed build
                result["status"], result["error"] = "failed", f"USD post-processing: {exc}"
                return result
        check = validate_usd(result["usd"], human_dir / f"{spec['id']}.json",
                             cfg["landmarks"].get("bone_prefix", "LM_"),
                             int(export["usd"].get("max_bone_influences", 4)))
        result["validation"] = check
        if check["status"] == "failed":
            result["status"], result["error"] = "failed", f"USD validation: {check['errors'][:2]}"
        elif check["status"] == "warn":
            result["status"] = "warn"
            result.setdefault("warnings", []).extend(check["warnings"])
        anim_cfg = export.get("animation") or {}
        if anim_cfg.get("enabled") and result["status"] != "failed":
            try:
                result["animation"] = str(write_animation(Path(result["usd"]), anim_cfg))
            except Exception as exc:  # noqa: BLE001 - animation is optional
                _LOG.warning(f"{spec['id']}: animation not written: {exc}")
    return result


def _postprocess(usd_path, meta_path: Path, post_cfg: dict) -> dict:
    """export.yaml -> usd_post on the exported USD (clothing hole faces, anatomy purpose, root joint);
    the outcome is recorded in <id>.json -> usd_post."""
    import json
    from ..usd_post import postprocess
    meta = json.loads(meta_path.read_text())
    garments = [i.get("asset") for i in (meta.get("clothing") or {}).get("items", []) if i.get("asset")]
    info = postprocess(usd_path, garments, post_cfg)
    root = info.get("root_joint") or {}
    if root.get("added"):                       # landmark joint paths now start below the new root joint
        for lm in (meta.get("landmarks") or {}).values():
            if isinstance(lm, dict) and lm.get("usd_joint") and not lm["usd_joint"].startswith(root["name"] + "/"):
                lm["usd_joint"] = f"{root['name']}/{lm['usd_joint']}"
    meta["usd_post"] = info
    meta_path.write_text(json.dumps(meta, indent=2))
    _LOG.info(f"{meta.get('id')}: USD post-processing {info}")
    return info


def write_animation(usd_path: Path, anim_cfg: dict) -> Path:
    """<id>_anim.usda: the human referenced + procedural UsdSkelAnimation (isaac/animate_human.py)."""
    import importlib
    import sys
    isaac_dir = str(Path(__file__).resolve().parents[2] / "isaac")
    if isaac_dir not in sys.path:
        sys.path.insert(0, isaac_dir)
    motion, animate = importlib.import_module("motion"), importlib.import_module("animate_human")
    cfg = dict(motion.DEFAULTS, **{k: v for k, v in anim_cfg.items() if k != "enabled"})
    return animate.build_scene(usd_path, usd_path.with_name(f"{usd_path.stem}_anim.usda"), cfg)


def _select_specs(manifest: dict, ctx, results: dict, only, resume: bool) -> list:
    specs = manifest["humans"]
    if only:
        wanted = set(only)
        unknown = wanted - {s["id"] for s in specs}
        if unknown:
            raise ValueError(f"unknown human ids {sorted(unknown)} (not in manifest)")
        return [s for s in specs if s["id"] in wanted]
    if resume:
        return [s for s in specs if results.get(s["id"], {}).get("status") not in ("ok", "warn")
                or not (ctx.human_dir(s["id"]) / f"{s['id']}.json").exists()]
    return specs


def _sample(cfg: dict, ctx) -> dict:
    started = time.monotonic()
    catalogue = load_target_catalogue(resolve_mpfb_data_dir(cfg["export"].get("mpfb_data_dir", "auto")))
    specs = build_specs(cfg, catalogue)
    write_manifest(ctx.manifest_path, ctx.run_id, cfg, specs)
    manifest = read_manifest(ctx.manifest_path)
    counts = {}
    for key in ("sex", "ethnicity", "somatotype"):
        counts[key] = {}
        for spec in specs:
            counts[key][spec[key]] = counts[key].get(spec[key], 0) + 1
    _LOG.info(f"[sample]    {len(specs)} humans | " +
              " | ".join(" ".join(f"{k} {v}" for k, v in c.items()) for c in counts.values()) +
              f" | {time.monotonic() - started:.1f}s -> {ctx.manifest_path}")
    return manifest


def run_pipeline(cfg: dict, config_dir, run_dir=None, resume=False, only=None, skip_preflight=False,
                 gown_generator=None, install_packs=False) -> int:
    """Returns a process exit code: 0 all ok/warn, 1 some humans failed, 2 preflight/config failure."""
    ctx = open_run(run_dir) if run_dir else create_run(cfg["export"]["output_root"], cfg["export"]["run_dir_format"])
    central_log = setup_run_logging(cfg["logging"], ctx.run_dir, ctx.run_id)
    _LOG.info(f"[run]       {ctx.run_id} -> {ctx.run_dir}")
    _LOG.debug(f"central log copy: {central_log}")
    started = time.monotonic()

    if not skip_preflight:
        checks = preflight.run_preflight(cfg, auto_fix=True, gown_generator=gown_generator,
                                         install_packs=install_packs)
        (ctx.run_dir / "preflight.json").write_text(json.dumps(preflight.environment_summary(checks), indent=2))
        if not preflight.report(checks):
            _LOG.error("[preflight] failed - fix the errors above and run again")
            return 2

    if run_dir:
        manifest = read_manifest(ctx.manifest_path)
        _LOG.info(f"[sample]    reusing manifest with {manifest['count']} humans")
    else:
        snapshot_config(ctx, cfg, config_dir)
        manifest = _sample(cfg, ctx)

    results = _load_results(ctx)
    try:
        todo = _select_specs(manifest, ctx, results, only, resume)
    except ValueError as exc:
        _LOG.error(f"[build]     {exc}")
        return 2
    workers = max(1, int(cfg["export"].get("workers", 1)))
    _LOG.info(f"[build]     {len(todo)} to build with {workers} worker(s)"
              + (f" ({len(manifest['humans']) - len(todo)} already done)" if resume else ""))
    progress = Progress(len(todo))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="worker") as pool:
        futures = {}
        for spec in todo:
            progress.start_item(spec)
            futures[pool.submit(_build_one, cfg, ctx, spec)] = spec
        for future in as_completed(futures):
            spec = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001 - one failure must not stop the run
                _LOG.exception(f"{spec['id']}: orchestrator error")
                result = {"status": "failed", "error": str(exc)}
            results[spec["id"]] = result
            _save_results(ctx, results)
            progress.finish_item(spec, result)

    metadata = report.load_metadata(ctx.humans_dir)
    statuses = {hid: r.get("status") for hid, r in results.items()}
    report.write_population_csv(ctx.run_dir / "population.csv", metadata, statuses)
    summary = report.write_summary(ctx.run_dir / "summary.json", cfg, ctx.run_id, metadata, results,
                                   time.monotonic() - started)
    report.write_contact_sheet(ctx.run_dir / "contact_sheet.png", ctx.humans_dir, [m["id"] for m in metadata])

    total = len(metadata)
    _LOG.info("[report]    configured vs achieved")
    for name, dist in summary["distributions"].items():
        print_distribution_table(name, dist["configured_pct"], dist["achieved"], total)
    for key, stats in summary["body_stats"].items():
        if stats:
            _LOG.info(f"  {key:<10} min {stats['min']:>7}  mean {stats['mean']:>7}  max {stats['max']:>7}")
    counts = summary["status_counts"]
    _LOG.info(f"[done]      {ctx.run_id} | {counts.get('ok', 0)} ok, {counts.get('warn', 0)} warn, "
              f"{counts.get('failed', 0)} failed | total {fmt_duration(time.monotonic() - started)} -> {ctx.run_dir}")
    return 1 if counts.get("failed") else 0
