#!/usr/bin/env python3
"""Generate synthetic X-ray rooms: preflight -> sample (spec + layout) -> build USD -> validate -> report.

    python scripts/run_pipeline.py                                   # new run-<timestamp> (variations.count rooms)
    python scripts/run_pipeline.py --count 3 --workers 1             # quick test
    python scripts/run_pipeline.py --set room.footprint_ft=[20,10]   # any config value, dotted key = YAML value
    python scripts/run_pipeline.py --height 2.9                      # fixed room height (m); or --set room.ceiling_height_ft=9
    python scripts/run_pipeline.py --resume --run-dir <run dir>      # continue an interrupted run
    python scripts/run_pipeline.py --only R0002 --run-dir <run dir>  # rebuild one room (same spec + layout)

Exit codes: 0 success (ok/warn), 1 some rooms failed, 2 configuration or preflight error.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_room.config import NULL, ConfigError, load_config, parse_set_args  # noqa: E402
from sdg_room.logging_setup import setup_console_only  # noqa: E402
from sdg_room.paths import CONFIG_DIR  # noqa: E402
from sdg_room.pipeline.orchestrator import run_pipeline  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(CONFIG_DIR), help="config directory (default: room/configs)")
    parser.add_argument("--count", type=int, help="override variations.count")
    parser.add_argument("--seed", type=int, help="override variations.seed")
    parser.add_argument("--workers", type=int, help="override export.workers")
    parser.add_argument("--output-root", help="override export.output_root")
    parser.add_argument("--height", type=float, help="fixed room (ceiling) height in m, = --set room.ceiling_height_m=<h>")
    parser.add_argument("--set", action="append", metavar="KEY=VALUE", default=[],
                        help="override any config value, e.g. --set room.footprint_ft=[20,10] (repeatable)")
    parser.add_argument("--run-dir", help="existing run directory (with --resume or --only)")
    parser.add_argument("--resume", action="store_true", help="build only rooms not finished yet")
    parser.add_argument("--only", action="append", metavar="ID", help="build only this room id (repeatable)")
    parser.add_argument("--skip-preflight", action="store_true", help="skip environment checks (not recommended)")
    args = parser.parse_args(argv)
    if (args.resume or args.only) and not args.run_dir:
        parser.error("--resume / --only need --run-dir")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        overrides = parse_set_args(args.set)
        overrides.update({"variations.count": args.count, "variations.seed": args.seed,
                          "export.workers": args.workers, "export.output_root": args.output_root,
                          "room.ceiling_height_m": args.height})
        if args.height is not None:
            overrides["room.ceiling_height_ft"] = NULL
        cfg = load_config(args.config, overrides)
    except ConfigError as exc:
        setup_console_only()
        print(f"[config] {exc}")
        return 2
    return run_pipeline(cfg, args.config, run_dir=args.run_dir, resume=args.resume, only=args.only,
                        skip_preflight=args.skip_preflight)


if __name__ == "__main__":
    sys.exit(main())
