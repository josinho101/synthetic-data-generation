"""MakeHuman asset packs (hair, skins, garments): find, download and install them (stdlib only).

Packs listed in export.yaml -> asset_packs are extracted into MPFB's user data directory, the
same place MPFB's "Install pack from zip" uses. Every pack zip carries packs/<name>.json, which is
how an installed pack is recognised.
"""

import logging
import shutil
import urllib.request
import zipfile
from pathlib import Path

from .mpfb_locate import find_mpfb_dirs, user_data_dir

_LOG = logging.getLogger("sdg_humans.asset_packs")

ALLOWED = {".mhclo", ".mhmat", ".obj", ".png", ".jpg", ".jpeg", ".thumb", ".mhw", ".proxy", ".json", ".txt",
           ".mhpxy", ".bvh", ".target", ".gz", ".tif", ".tga", ".bmp", ".mhskel", ".mhm", ".mhpose", ".npz", ".md",
           ".license", ".mhwt"}
DEFAULT_DOWNLOAD_DIR = "~/.cache/sdg_asset_packs"


def target_dir(cfg: dict):
    """MPFB user data dir (None when MPFB is not installed)."""
    configured = cfg["export"].get("asset_packs_target", "auto")
    if configured and configured != "auto":
        return Path(configured).expanduser()
    dirs = find_mpfb_dirs()
    return user_data_dir(dirs[0]) if dirs else None


def installed_packs(target) -> set:
    folder = Path(target) / "packs" if target else None
    return {p.stem for p in folder.glob("*.json")} if folder and folder.exists() else set()


def missing_packs(cfg: dict, target=None) -> list:
    target = target or target_dir(cfg)
    have = installed_packs(target)
    return [p for p in cfg["export"].get("asset_packs", []) if p["name"] not in have]


def safe_extract(zip_path: Path, target: Path) -> int:
    """Extract data files only; refuses absolute paths and '..'. Returns the number of files."""
    count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            if info.is_dir():
                continue
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in {zip_path.name}: {name}")
            if Path(name).suffix.lower() not in ALLOWED:
                _LOG.debug(f"skip {name} (not an asset file type)")
                continue
            out = target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
            count += 1
    return count


def _download(url: str, dest: Path) -> None:
    part = dest.with_suffix(dest.suffix + ".part")
    last = [-1]

    def hook(blocks, block_size, total):
        if total > 0:
            pct = min(100, blocks * block_size * 100 // total)
            if pct // 10 != last[0]:
                last[0] = pct // 10
                _LOG.info(f"[packs]     {dest.name:<34} {pct:>3}% of {total / 1e6:.0f} MB")

    urllib.request.urlretrieve(url, part, hook)
    if not zipfile.is_zipfile(part):
        part.unlink()
        raise ValueError(f"download of {url} is not a zip file")
    part.replace(dest)


def install(cfg: dict, only_missing=True, from_dir=None, download_dir=None) -> list:
    """Download (unless the zip is already in from_dir / download_dir) and install packs.

    Returns [{name, status: installed|skipped|failed, files, detail}]."""
    export = cfg["export"]
    target = target_dir(cfg)
    if target is None:
        raise RuntimeError("MPFB not found - install the MPFB extension in Blender first")
    source = Path(from_dir or download_dir or export.get("asset_packs_download_dir") or DEFAULT_DOWNLOAD_DIR)
    source = source.expanduser()
    source.mkdir(parents=True, exist_ok=True)
    target.mkdir(parents=True, exist_ok=True)
    todo = missing_packs(cfg, target) if only_missing else list(export.get("asset_packs", []))
    have = {p["name"] for p in export.get("asset_packs", [])} - {p["name"] for p in todo}
    results = [{"name": n, "status": "skipped", "files": 0, "detail": "already installed"} for n in sorted(have)]
    for pack in todo:
        zip_path = source / pack["file"]
        try:
            if not zip_path.exists():
                if from_dir:
                    raise FileNotFoundError(f"{zip_path} not found")
                url = f"{export['asset_packs_url']}/{pack['name']}/{pack['file']}"
                _LOG.info(f"[packs]     downloading {url}")
                _download(url, zip_path)
            files = safe_extract(zip_path, target)
            results.append({"name": pack["name"], "status": "installed", "files": files, "detail": pack["license"]})
            _LOG.info(f"[packs]     installed {pack['name']:<24} {files:>5} files ({pack['license']}) -> {target}")
        except Exception as exc:  # one bad pack must not hide the others
            results.append({"name": pack["name"], "status": "failed", "files": 0, "detail": str(exc)})
            _LOG.error(f"[packs]     {pack['name']} failed: {exc}")
    return results
