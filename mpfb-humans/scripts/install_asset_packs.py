#!/usr/bin/env python3
"""Download and install the MakeHuman asset packs listed in configs/export.yaml (asset_packs).

    python scripts/install_asset_packs.py                       # download + install the missing packs
    python scripts/install_asset_packs.py --all                 # reinstall every pack
    python scripts/install_asset_packs.py --from-dir ~/packs    # offline: install zips copied to ~/packs
    python scripts/install_asset_packs.py --list                # show what is installed

Packs are extracted into MPFB's user data directory (same as MPFB's "Install pack from zip").
Only data files are accepted (no absolute paths, no "..", no scripts).
The same install also runs from run_pipeline.py / check_env.py with --install-packs.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans import asset_packs  # noqa: E402
from sdg_humans.config import load_config  # noqa: E402
from sdg_humans.logging_setup import setup_console_only  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs")
    parser.add_argument("--from-dir", help="directory that already contains the zip files (no download)")
    parser.add_argument("--download-dir", help="where downloaded zips are kept "
                                               "(default: export.asset_packs_download_dir)")
    parser.add_argument("--all", action="store_true", help="reinstall packs that are already installed")
    parser.add_argument("--list", action="store_true", help="show installed packs and asset counts")
    args = parser.parse_args()
    setup_console_only()
    cfg = load_config(args.config, validate_config=False)
    target = asset_packs.target_dir(cfg)
    if target is None:
        print("MPFB not found - install the MPFB extension in Blender first (docs/02_setup.md)")
        return 2
    if args.list:
        print(f"MPFB user data: {target}")
        have = asset_packs.installed_packs(target)
        for pack in cfg["export"].get("asset_packs", []):
            print(f"  pack {pack['name']:<26} {'installed' if pack['name'] in have else 'MISSING'}")
        for sub in ("skins", "hair", "eyebrows", "eyelashes", "eyes", "clothes"):
            items = sorted(p.name for p in (target / sub).glob("*") if p.is_dir()) if (target / sub).exists() else []
            print(f"  {sub:<10} {len(items):>4}  {', '.join(items[:10])}{' ...' if len(items) > 10 else ''}")
        return 0
    results = asset_packs.install(cfg, only_missing=not args.all, from_dir=args.from_dir,
                                  download_dir=args.download_dir)
    failed = [r for r in results if r["status"] == "failed"]
    for r in results:
        print(f"  {r['name']:<26} {r['status']:<9} {r['detail']}")
    print("done - run scripts/check_env.py to verify" if not failed else f"{len(failed)} pack(s) failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
