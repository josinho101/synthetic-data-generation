#!/usr/bin/env python3
"""Validate exported human USD files for Isaac Sim compatibility.

    python scripts/validate_usd.py <run dir>          # every human of a run
    python scripts/validate_usd.py <path/H0001.usd>   # one file (uses H0001.json next to it if present)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans.pipeline.validate import validate_usd  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target")
    parser.add_argument("--json", action="store_true", help="print full JSON results")
    args = parser.parse_args()
    target = Path(args.target)
    files = sorted(p for p in target.glob("humans/*/*.usd*") if not p.stem.endswith("_anim")) if target.is_dir() else [target]
    failed = 0
    for usd in files:
        result = validate_usd(usd, usd.with_suffix(".json"))
        failed += result["status"] == "failed"
        print(f"{result['status'].upper():<6} {usd.name:<14} joints {result.get('joint_count', 0):>4} "
              f"(landmarks {result.get('landmark_joint_count', 0)}) meshes {result.get('mesh_count', 0)} "
              f"height {result.get('bounds_height_cm')} cm")
        for message in result["errors"] + result["warnings"]:
            print(f"       - {message}")
        if args.json:
            print(json.dumps(result, indent=2))
    print(f"{len(files) - failed}/{len(files)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
