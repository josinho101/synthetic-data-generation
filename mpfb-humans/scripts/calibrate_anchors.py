#!/usr/bin/env python3
"""Propose landmark anchor vertex IDs (headless) and write them into configs/landmarks.yaml.

    python scripts/calibrate_anchors.py --auto              # fill only anchors that are null
    python scripts/calibrate_anchors.py --auto --overwrite  # replace all anchors
    python scripts/calibrate_anchors.py --auto --dry-run    # print, do not write
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans.config import load_config  # noqa: E402
from sdg_humans.logging_setup import setup_console_only  # noqa: E402
from sdg_humans.paths import CENTRAL_LOG_DIR  # noqa: E402
from sdg_humans.pipeline.blender_runner import run_task  # noqa: E402


def write_anchors(yaml_path: Path, anchors: dict, overwrite: bool) -> list:
    """Replace '  name: <value>' lines in the anchors block, keeping comments intact."""
    text = yaml_path.read_text(encoding="utf-8")
    changed = []
    for name, vertex in anchors.items():
        pattern = re.compile(rf"^(  {re.escape(name)}:\s*)(null|\d+)(.*)$", re.M)
        match = pattern.search(text)
        if not match or (match.group(2) != "null" and not overwrite):
            continue
        text = text[:match.start()] + f"{match.group(1)}{vertex}{match.group(3)}" + text[match.end():]
        changed.append(name)
    yaml_path.write_text(text, encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs", help="config directory")
    parser.add_argument("--auto", action="store_true", required=True, help="headless proposal")
    parser.add_argument("--overwrite", action="store_true", help="replace already calibrated anchors")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    setup_console_only()

    cfg = load_config(args.config, validate_config=False)
    export = cfg["export"]
    print("[calibrate] running anchor proposal in headless Blender ...")
    result = run_task(export["blender_bin"], "calibrate", {"mpfb_module": export.get("mpfb_module", "auto")},
                      CENTRAL_LOG_DIR / "calibrate_anchors.log", timeout_s=600)
    if result.get("status") != "ok":
        print(f"[calibrate] FAILED: {result.get('error')} (log: {result.get('log')})")
        return 1
    for name, vertex in result["anchors"].items():
        print(f"  {name:<24} vertex {vertex:>6}  at {result['positions'][name]}")
    if args.dry_run:
        return 0
    changed = write_anchors(Path(args.config) / "landmarks.yaml", result["anchors"], args.overwrite)
    print(f"[calibrate] updated {len(changed)} anchors in {Path(args.config) / 'landmarks.yaml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
