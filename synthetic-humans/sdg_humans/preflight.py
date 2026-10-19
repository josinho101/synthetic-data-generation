"""Environment checks run before every pipeline start (also: scripts/check_env.py).

Each check yields a CheckResult with status ok / warn / error. Any error stops the run.
"""

import importlib
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import asset_packs
from .mpfb_locate import find_mpfb_dirs, read_manifest_version
from .paths import ASSETS_DIR, CENTRAL_LOG_DIR, PROJECT_ROOT
from .pipeline.blender_runner import run_task

_LOG = logging.getLogger("sdg_humans.preflight")


@dataclass
class CheckResult:
    name: str
    status: str  # ok | warn | error
    detail: str
    data: dict = field(default_factory=dict)


def _version_tuple(text: str) -> tuple:
    parts = []
    for piece in str(text).replace("-", ".").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def check_python(cfg) -> CheckResult:
    need = _version_tuple(cfg["export"].get("min_python", "3.10"))
    have = sys.version_info[:3]
    ok = have >= need
    return CheckResult("python", "ok" if ok else "error",
                       f"Python {'.'.join(map(str, have))}" + ("" if ok else f" < required {'.'.join(map(str, need))}"))


def check_packages(_cfg) -> CheckResult:
    missing = []
    for module, package in (("yaml", "pyyaml"), ("numpy", "numpy"), ("pxr", "usd-core"), ("PIL", "pillow")):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(package)
    if missing:
        return CheckResult("python packages", "error", f"missing {missing}: pip install -r requirements.txt")
    return CheckResult("python packages", "ok", "pyyaml, numpy, usd-core, pillow")


def check_blender_binary(cfg) -> CheckResult:
    exe = cfg["export"]["blender_bin"]
    path = shutil.which(exe) or (exe if Path(exe).exists() else None)
    if not path:
        return CheckResult("blender", "error", f"Blender not found at '{exe}' (export.blender_bin)")
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("blender", "error", f"cannot run {path}: {exc}")
    line = next((ln for ln in out.splitlines() if ln.startswith("Blender ")), "Blender ?")
    version = line.split()[1]
    if _version_tuple(version) < _version_tuple(cfg["export"]["min_blender"]):
        return CheckResult("blender", "error", f"{line} < required {cfg['export']['min_blender']}")
    tested = str(cfg["export"].get("tested_blender", ""))
    status = "ok" if not tested or version.startswith(tested) else "warn"
    note = "" if status == "ok" else f" (tested with {tested}.x)"
    return CheckResult("blender", status, f"{line}{note}", {"path": path, "version": version})


def check_mpfb_on_disk(cfg) -> CheckResult:
    dirs = find_mpfb_dirs()
    if not dirs and cfg["export"].get("mpfb_data_dir", "auto") == "auto":
        return CheckResult("mpfb", "error", "MPFB extension not found; install it in Blender (Get Extensions -> MPFB)")
    version = read_manifest_version(dirs[0]) if dirs else "unknown"
    if dirs and _version_tuple(version) < _version_tuple(cfg["export"]["min_mpfb"]):
        return CheckResult("mpfb", "error", f"MPFB {version} < required {cfg['export']['min_mpfb']}")
    return CheckResult("mpfb", "ok", f"MPFB {version} at {dirs[0] if dirs else cfg['export']['mpfb_data_dir']}",
                       {"version": version})


def check_blender_probe(cfg) -> list:
    """Start Blender once: MPFB import, asset counts, GPU devices."""
    result = run_task(cfg["export"]["blender_bin"], "probe", {"mpfb_module": cfg["export"].get("mpfb_module", "auto")},
                      CENTRAL_LOG_DIR / "preflight_probe.log", timeout_s=300)
    if result.get("status") != "ok":
        return [CheckResult("mpfb import", "error", f"MPFB could not be loaded in Blender: {result.get('error')}")]
    checks = [CheckResult("mpfb import", "ok", f"{result['mpfb_module']} {result['mpfb_version']} "
                                                 f"(Blender {result['blender_version']})", result)]
    counts = result["asset_counts"]
    summary = ", ".join(f"{k} {v}" for k, v in counts.items())
    if not result.get("system_assets_installed") and counts.get("skins", 0) == 0:
        status = "error" if cfg["export"].get("asset_mode") == "required" else "warn"
        checks.append(CheckResult("asset packs", status,
                                  f"no MakeHuman system assets ({summary}); using procedural skin, generated eyes, "
                                  "no hair/eyebrows/eyelashes/footwear - run with --install-packs (docs/02_setup.md)", counts))
    else:
        checks.append(CheckResult("asset packs", "ok", summary, counts))
    gpus = result.get("gpu_devices") or []
    checks.append(CheckResult("gpu (bake)", "ok" if gpus else "warn",
                              ", ".join(gpus) if gpus else "no GPU visible to Cycles; texture bake runs on CPU"))
    return checks


def check_gowns(cfg) -> CheckResult:
    missing = []
    for name, variant in cfg["clothing"]["variants"].items():
        if variant["pct"] <= 0:
            continue
        for slot in variant["slots"].values():
            if "asset" in slot:
                p = Path(slot["asset"])
                p = p if p.is_absolute() else ASSETS_DIR / p
                if not p.exists():
                    missing.append(str(p.relative_to(PROJECT_ROOT)) if PROJECT_ROOT in p.parents else str(p))
    if missing:
        return CheckResult("clothing assets", "error", f"missing {sorted(set(missing))}", {"missing": missing})
    return CheckResult("clothing assets", "ok", "all fixed clothing assets present")


def check_anchors(cfg) -> CheckResult:
    missing = [k for k, v in cfg["landmarks"]["anchors"].items() if v is None]
    if missing:
        return CheckResult("landmark anchors", "error",
                           f"{len(missing)} anchors not calibrated: run scripts/calibrate_anchors.py --auto")
    return CheckResult("landmark anchors", "ok", f"{len(cfg['landmarks']['anchors'])} anchors calibrated")


def check_output(cfg) -> CheckResult:
    root = Path(cfg["export"]["output_root"])
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        return CheckResult("output dir", "error", f"{root} is not writable: {exc}")
    free_mb = shutil.disk_usage(root).free / 1e6
    need_mb = cfg["population"]["count"] * float(cfg["export"].get("est_mb_per_human", 60))
    status = "ok" if free_mb > need_mb else "warn"
    return CheckResult("output dir", status, f"{root} writable, {free_mb / 1000:.1f} GB free "
                                             f"(need ~{need_mb / 1000:.1f} GB)")


def check_asset_packs(cfg, install=False) -> CheckResult:
    """Configured packs (export.asset_packs) vs installed; installs the missing ones when asked."""
    missing = asset_packs.missing_packs(cfg)
    if missing and install:
        _LOG.info(f"[preflight] installing {len(missing)} missing asset pack(s) (one-time download) ...")
        asset_packs.install(cfg)
        missing = asset_packs.missing_packs(cfg)
    total = len(cfg["export"].get("asset_packs", []))
    if not missing:
        return CheckResult("asset packs cfg", "ok", f"{total}/{total} configured packs installed")
    names = ", ".join(p["name"] for p in missing)
    status = "error" if cfg["export"].get("asset_mode") == "required" else "warn"
    return CheckResult("asset packs cfg", status, f"missing {len(missing)}/{total}: {names} - run with "
                       "--install-packs or scripts/install_asset_packs.py", {"missing": [p["name"] for p in missing]})


def run_preflight(cfg, auto_fix=True, gown_generator=None, install_packs=False) -> list:
    """Run all checks. With auto_fix, missing gown assets are generated (gown_generator(cfg)).
    With install_packs (or export.install_missing_packs), missing asset packs are downloaded."""
    checks = [check_python(cfg), check_packages(cfg), check_blender_binary(cfg), check_mpfb_on_disk(cfg)]
    if any(c.status == "error" for c in checks):
        return checks
    checks.append(check_asset_packs(cfg, install_packs or bool(cfg["export"].get("install_missing_packs"))))
    checks += check_blender_probe(cfg)
    gowns = check_gowns(cfg)
    if gowns.status == "error" and auto_fix and gown_generator is not None:
        _LOG.info("[preflight] gown assets missing - generating them now (one-time, a few minutes) ...")
        result = gown_generator(cfg)
        gowns = check_gowns(cfg)
        if result.get("status") != "ok":
            gowns.detail += f" (generation failed: {result.get('error')})"
    checks += [gowns, check_anchors(cfg), check_output(cfg)]
    return checks


def report(checks: list) -> bool:
    """Log one line per check; returns True when there is no error."""
    marks = {"ok": "OK  ", "warn": "WARN", "error": "FAIL"}
    for check in checks:
        line = f"[preflight] {marks[check.status]} {check.name:<17} {check.detail}"
        {"ok": _LOG.info, "warn": _LOG.warning, "error": _LOG.error}[check.status](line)
    return not any(c.status == "error" for c in checks)


def environment_summary(checks: list) -> dict:
    return {c.name: {"status": c.status, "detail": c.detail} for c in checks} | {"cwd": os.getcwd()}
