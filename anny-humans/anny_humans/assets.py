"""Locate the MakeHuman asset packs (skins, eyes, hair, eyebrows, eyelashes, clothes).

They are shared with the MPFB pipeline, which installs them into MPFB's user data directory
(mpfb-humans/scripts/install_asset_packs.py)."""

from pathlib import Path

ASSET_SUBDIRS = ("skins", "eyes", "hair", "eyebrows", "eyelashes", "clothes")


def resolve_assets_dir(value="auto"):
    """export.makehuman_assets_dir -> Path or None (nothing installed)."""
    if value and value != "auto":
        path = Path(value).expanduser()
        return path if path.is_dir() else None
    found = sorted(Path.home().glob(".config/blender/*/extensions/.user/*/mpfb/data"),
                   key=lambda p: tuple(int(x) if x.isdigit() else 0 for x in p.parts[-6].split(".")))
    found = [p for p in found if any((p / sub).is_dir() for sub in ASSET_SUBDIRS)]
    return found[-1] if found else None


def inventory(assets_dir) -> dict:
    """Asset counts per kind (0 when not installed)."""
    if assets_dir is None:
        return {sub: 0 for sub in ASSET_SUBDIRS}
    out = {}
    for sub in ASSET_SUBDIRS:
        pattern = "*/*.mhmat" if sub == "skins" else "*/*.mhclo"
        out[sub] = len(list(Path(assets_dir, sub).glob(pattern)))
    return out
