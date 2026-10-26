#!/usr/bin/env python3
"""Generate the hospital gown clothes assets (.mhclo/.obj/.mhmat) with MPFB MakeClothes services.

    python scripts/make_gown.py                       # all variants in configs/gown.yaml
    python scripts/make_gown.py --variant gown_short  # one variant
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans.config import load_config  # noqa: E402
from sdg_humans.logging_setup import setup_console_only  # noqa: E402
from sdg_humans.paths import CENTRAL_LOG_DIR, PROJECT_ROOT  # noqa: E402
from sdg_humans.pipeline.blender_runner import run_task  # noqa: E402


def generate(cfg: dict, variants=None) -> dict:
    gown_cfg = cfg["gown"]
    out_dir = Path(gown_cfg["output_dir"])
    out_dir = out_dir if out_dir.is_absolute() else PROJECT_ROOT / out_dir
    args = {"gown_cfg": gown_cfg, "out_dir": str(out_dir), "variants": variants,
            "mpfb_module": cfg["export"].get("mpfb_module", "auto")}
    return run_task(cfg["export"]["blender_bin"], "gown", args, CENTRAL_LOG_DIR / "make_gown.log", timeout_s=3600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs")
    parser.add_argument("--variant", action="append", help="only this variant (repeatable)")
    args = parser.parse_args()
    setup_console_only()
    cfg = load_config(args.config, validate_config=False)
    print("[gown] generating gown assets in headless Blender (about 1-2 min per variant) ...")
    result = generate(cfg, args.variant)
    if result.get("status") != "ok":
        print(f"[gown] FAILED: {result.get('error')} (log: {result.get('log')})")
        return 1
    for name, path in result["written"].items():
        print(f"  {name:<20} -> {path}")
    print(f"[gown] done in {result.get('duration_s', 0):.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
