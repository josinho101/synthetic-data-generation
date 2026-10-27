"""Pipeline orchestration: preflight -> sample -> build (worker threads sharing one Anny model) -> validate -> report."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .. import preflight
from ..assets import resolve_assets_dir
from ..logging_setup import human_log, setup_run_logging
from ..metadata import report
from ..preview import render_usd
from ..progress import Progress, fmt_duration, print_distribution_table
from ..run_context import create_run, open_run, snapshot_config
from ..sampling.face import load_target_catalogue
from ..sampling.manifest import build_specs, read_manifest, write_manifest
from .validate import validate_usd

_LOG = logging.getLogger("anny_humans.pipeline")


class Builder:
    """Shared, lazily loaded resources of a run (the Anny model is loaded once)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._body = None
        self._lock = threading.Lock()
        self.catalogue = load_target_catalogue()
        self.assets_dir = resolve_assets_dir(cfg["export"].get("makehuman_assets_dir", "auto"))

    @property
    def body(self):
        with self._lock:
            if self._body is None:
                from ..model import AnnyBody
                started = time.monotonic()
                self._body = AnnyBody(self.cfg["body"], self.cfg["export"].get("device", "auto"))
                _LOG.info(f"[model]     Anny ready in {time.monotonic() - started:.1f}s")
            return self._body


def _results_path(ctx) -> Path:
    return ctx.run_dir / "results.json"


def _load_results(ctx) -> dict:
    path = _results_path(ctx)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_results(ctx, results: dict) -> None:
    _results_path(ctx).write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


def _postprocess(usd_path, meta_path: Path, post_cfg: dict) -> dict:
    """export.yaml -> usd_post on the written USD (clothing hole faces, anatomy purpose, root joint);
    the outcome is recorded in <id>.json -> usd_post."""
    from ..usd_post import postprocess
    meta = json.loads(meta_path.read_text())
    # footwear is handled by hide_body_under (body vertices really inside the shoe are removed); as a hole source it
    # would also hide the visible instep above open shoes
    garments = [i.get("asset") for i in (meta.get("clothing") or {}).get("items", [])
                if i.get("asset") and not i.get("hides_body")]
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


def _build_one(builder: Builder, ctx, spec: dict) -> dict:
    """Build one human (with retries), post-process and validate its USD."""
    from .build import build_human
    cfg = builder.cfg
    export = cfg["export"]
    log = ctx.human_log(spec["id"])
    attempts = int(export.get("retries", 0)) + 1
    result = {}
    started = time.monotonic()
    with human_log(log, cfg["logging"].get("worker_level", "INFO"), cfg["logging"].get("worker_format")):
        for attempt in range(1, attempts + 1):
            try:
                result = build_human(builder.body, builder.catalogue, cfg, spec, ctx.human_dir(spec["id"]),
                                     ctx.run_id, builder.assets_dir)
                break
            except Exception as exc:  # noqa: BLE001 - reported per human, the run continues
                _LOG.exception(f"{spec['id']}: attempt {attempt}/{attempts} failed")
                result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        result["log"] = str(log)
        if result.get("status") in ("ok", "warn"):
            human_dir = ctx.human_dir(spec["id"])
            post_cfg = export.get("usd_post") or {}
            if post_cfg.get("enabled", True):
                try:
                    result["usd_post"] = _postprocess(result["usd"], human_dir / f"{spec['id']}.json", post_cfg)
                except Exception as exc:  # noqa: BLE001 - reported as a failed build
                    _LOG.exception(f"{spec['id']}: USD post-processing failed")
                    result["status"], result["error"] = "failed", f"USD post-processing: {exc}"
            if result["status"] != "failed":
                try:
                    preview_cfg = export.get("preview") or {}
                    started_preview = time.monotonic()
                    render_usd(result["usd"], human_dir / f"{spec['id']}.png", preview_cfg.get("resolution", [512, 768]),
                               preview_cfg.get("background_rgb", "#d9dde3"), spec["id"])
                    result.setdefault("timings", {})["preview"] = round(time.monotonic() - started_preview, 2)
                except Exception as exc:  # noqa: BLE001 - the preview is QA only
                    _LOG.exception(f"{spec['id']}: preview failed")
                    result.setdefault("warnings", []).append(f"preview not rendered: {exc}")
                check = validate_usd(result["usd"], human_dir / f"{spec['id']}.json",
                                     cfg["landmarks"].get("bone_prefix", "LM_"),
                                     int(export["usd"].get("max_bone_influences", 4)))
                result["validation"] = check
                if check["status"] == "failed":
                    result["status"], result["error"] = "failed", f"USD validation: {check['errors'][:2]}"
                elif check["status"] == "warn":
                    result["status"] = "warn"
                    result.setdefault("warnings", []).extend(check["warnings"])
    result["duration_s"] = round(time.monotonic() - started, 1)
    return result


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


def _sample(cfg: dict, ctx, catalogue: dict) -> dict:
    started = time.monotonic()
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


def run_pipeline(cfg: dict, config_dir, run_dir=None, resume=False, only=None, skip_preflight=False) -> int:
    """Returns a process exit code: 0 all ok/warn, 1 some humans failed, 2 preflight/config failure."""
    ctx = open_run(run_dir) if run_dir else create_run(cfg["export"]["output_root"], cfg["export"]["run_dir_format"])
    central_log = setup_run_logging(cfg["logging"], ctx.run_dir, ctx.run_id)
    _LOG.info(f"[run]       {ctx.run_id} -> {ctx.run_dir}")
    _LOG.debug(f"central log copy: {central_log}")
    started = time.monotonic()

    if not skip_preflight:
        checks = preflight.run_preflight(cfg)
        (ctx.run_dir / "preflight.json").write_text(json.dumps(checks, indent=2))
        if not preflight.report(checks):
            _LOG.error("[preflight] failed - fix the errors above and run again")
            return 2

    builder = Builder(cfg)
    if run_dir:
        manifest = read_manifest(ctx.manifest_path)
        _LOG.info(f"[sample]    reusing manifest with {manifest['count']} humans")
    else:
        snapshot_config(ctx, cfg, config_dir)
        manifest = _sample(cfg, ctx, builder.catalogue)

    results = _load_results(ctx)
    try:
        todo = _select_specs(manifest, ctx, results, only, resume)
    except ValueError as exc:
        _LOG.error(f"[build]     {exc}")
        return 2
    workers = max(1, int(cfg["export"].get("workers", 1)))
    _LOG.info(f"[build]     {len(todo)} to build with {workers} worker(s)"
              + (f" ({len(manifest['humans']) - len(todo)} already done)" if resume else ""))
    if todo:
        builder.body  # noqa: B018 - load the model once before the workers start
    progress = Progress(len(todo))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="worker") as pool:
        futures = {}
        for spec in todo:
            progress.start_item(spec)
            futures[pool.submit(_build_one, builder, ctx, spec)] = spec
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
