"""Find the MPFB installation on disk without starting Blender (stdlib only)."""

import re
from pathlib import Path

_SEARCH_ROOTS = [
    Path.home() / ".config" / "blender",                     # Linux
    Path.home() / "snap" / "blender" / "common" / ".config" / "blender",
    Path.home() / "Library" / "Application Support" / "Blender",  # macOS
    Path.home() / "AppData" / "Roaming" / "Blender Foundation" / "Blender",  # Windows
]


def _version_key(path: Path):
    nums = re.findall(r"\d+", str(path))
    return [int(n) for n in nums]


def find_mpfb_dirs() -> list:
    """All MPFB extension dirs (newest Blender version first)."""
    found = []
    for root in _SEARCH_ROOTS:
        if root.exists():
            found.extend(p.parent for p in root.glob("*/extensions/*/mpfb/blender_manifest.toml"))
    return sorted(set(found), key=_version_key, reverse=True)


def resolve_mpfb_data_dir(configured: str = "auto"):
    if configured and configured != "auto":
        return Path(configured)
    dirs = find_mpfb_dirs()
    return dirs[0] / "data" if dirs else None


def read_manifest_version(mpfb_dir: Path):
    manifest = Path(mpfb_dir) / "blender_manifest.toml"
    if not manifest.exists():
        return None
    match = re.search(r'^version\s*=\s*"([^"]+)"', manifest.read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else None


def user_data_dir(mpfb_dir: Path) -> Path:
    """MPFB 2.x keeps user assets in extensions/.user/<repo>/mpfb/data."""
    mpfb_dir = Path(mpfb_dir)
    return mpfb_dir.parent.parent / ".user" / mpfb_dir.parent.name / "mpfb" / "data"
