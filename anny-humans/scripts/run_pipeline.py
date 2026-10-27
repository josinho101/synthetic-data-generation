#!/usr/bin/env python3
"""Generate synthetic humans from the Anny body model: preflight -> sample -> build -> validate -> report.

    python scripts/run_pipeline.py                                  # new run-<timestamp>
    python scripts/run_pipeline.py --count 5                        # quick test
    python scripts/run_pipeline.py --age-min 30 --age-max 60        # override population.age_range
    python scripts/run_pipeline.py --resume --run-dir <run dir>     # continue an interrupted run
    python scripts/run_pipeline.py --only A0042 --run-dir <run dir> # rebuild one human

Exit codes: 0 success (ok/warn), 1 some humans failed, 2 configuration or preflight error.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anny_humans.config import ConfigError, load_config  # noqa: E402
from anny_humans.logging_setup import setup_console_only  # noqa: E402
from anny_humans.pipeline.orchestrator import run_pipeline  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs"), help="config directory (default: configs)")
    parser.add_argument("--count", type=int, help="override population.count")
    parser.add_argument("--seed", type=int, help="override population.seed")
    parser.add_argument("--age-min", type=int, help="override population.age_range.min (>= 18)")
    parser.add_argument("--age-max", type=int, help="override population.age_range.max (<= 70)")
    parser.add_argument("--workers", type=int, help="override export.workers")
    parser.add_argument("--output-root", help="override export.output_root")
    parser.add_argument("--run-dir", help="existing run directory (with --resume or --only)")
    parser.add_argument("--resume", action="store_true", help="build only humans not finished yet")
    parser.add_argument("--only", action="append", metavar="ID", help="build only this human id (repeatable)")
    parser.add_argument("--skip-preflight", action="store_true", help="skip environment checks (not recommended)")
    args = parser.parse_args(argv)
    if (args.resume or args.only) and not args.run_dir:
        parser.error("--resume / --only need --run-dir")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    overrides = {"population.count": args.count, "population.seed": args.seed,
                 "population.age_range.min": args.age_min, "population.age_range.max": args.age_max,
                 "export.workers": args.workers, "export.output_root": args.output_root}
    try:
        cfg = load_config(args.config, overrides)
    except ConfigError as exc:
        setup_console_only()
        print(f"[config] {exc}")
        return 2
    return run_pipeline(cfg, args.config, run_dir=args.run_dir, resume=args.resume, only=args.only,
                        skip_preflight=args.skip_preflight)


if __name__ == "__main__":
    sys.exit(main())
