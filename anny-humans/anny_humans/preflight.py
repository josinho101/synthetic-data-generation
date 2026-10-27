"""Environment checks before a run: Python packages, Anny, device, asset packs, output space, config sanity."""

import importlib
import logging
import shutil
import sys
from pathlib import Path

from .assets import inventory, resolve_assets_dir
from .paths import CUSTOM_ASSETS_DIR

_LOG = logging.getLogger("anny_humans.preflight")


def _version_tuple(text: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in str(text).split(".")[:3])


def run_preflight(cfg: dict) -> list:
    """-> [{name, status (ok | warn | error), detail}]."""
    export = cfg["export"]
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    py = ".".join(map(str, sys.version_info[:3]))
    add("python", "ok" if _version_tuple(py) >= _version_tuple(export.get("min_python", "3.10")) else "error", py)
    for module in ("numpy", "scipy", "trimesh", "PIL", "yaml", "pxr", "torch"):
        try:
            mod = importlib.import_module(module)
            add(module, "ok", getattr(mod, "__version__", "installed"))
        except ImportError as exc:
            add(module, "error", f"not importable: {exc}")
    try:
        from importlib.metadata import version
        anny_version = version("anny")
        ok = _version_tuple(anny_version) >= _version_tuple(export.get("min_anny", "0.6.0"))
        add("anny", "ok" if ok else "error", anny_version)
    except Exception as exc:  # noqa: BLE001
        add("anny", "error", f"not installed: {exc} (pip install anny)")
    device = export.get("device", "auto")
    try:
        import torch
        cuda = torch.cuda.is_available()
        if device == "cuda" and not cuda:
            add("device", "error", "export.device=cuda but CUDA is not available")
        else:
            add("device", "ok", ("cuda: " + torch.cuda.get_device_name(0)) if cuda and device != "cpu" else "cpu")
    except ImportError:
        pass

    assets_dir = resolve_assets_dir(export.get("makehuman_assets_dir", "auto"))
    counts = inventory(assets_dir)
    if assets_dir is None or not counts["skins"]:
        status = "error" if export.get("asset_mode") == "required" else "warn"
        add("asset_packs", status, "no MakeHuman system assets found (flat skin, generated eyes, no hair / clothes); "
                                   "install with mpfb-humans/scripts/install_asset_packs.py")
    else:
        add("asset_packs", "ok", f"{assets_dir}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    skirt = CUSTOM_ASSETS_DIR / "custom" / "hospital_gown" / "office_skirt.mhclo"
    add("office_skirt", "ok" if skirt.exists() else "warn",
        str(skirt) if skirt.exists() else f"{skirt} missing (skirt slots fall back per clothing.fallback_if_missing)")

    anchors = (cfg.get("landmarks") or {}).get("anchors") or {}
    missing = [k for k, v in anchors.items() if v is None]
    add("landmark_anchors", "error" if missing else "ok",
        f"not calibrated: {missing[:5]}" if missing else f"{len(anchors)} anchors (hm08 vertex IDs)")

    out = Path(export["output_root"])
    out.mkdir(parents=True, exist_ok=True)
    free_mb = shutil.disk_usage(out).free / 2 ** 20
    need = float(export.get("est_mb_per_human", 60)) * int(cfg["population"]["count"])
    add("disk", "ok" if free_mb > need else "error", f"{free_mb:.0f} MB free, ~{need:.0f} MB needed in {out}")
    return checks


def report(checks: list) -> bool:
    """Log the checks; True when nothing is an error."""
    for c in checks:
        log = _LOG.error if c["status"] == "error" else (_LOG.warning if c["status"] == "warn" else _LOG.info)
        log(f"[preflight] {c['status'].upper():<5} {c['name']:<17} {c['detail']}")
    return not any(c["status"] == "error" for c in checks)
