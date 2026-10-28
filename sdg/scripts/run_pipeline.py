#!/usr/bin/env python3
"""Animate synthetic patients doing X-ray exams in the generated X-ray rooms, live in Isaac Sim.

    python scripts/run_pipeline.py                                   # 2 humans x 1 room from the latest runs, GUI
    python scripts/run_pipeline.py --headless                        # same, no window
    python scripts/run_pipeline.py --humans 5 --rooms 2              # first 5 humans, first 2 rooms
    python scripts/run_pipeline.py --human-ids H0003,H0010 --room-ids R0002
    python scripts/run_pipeline.py --humans-root ../output/humans/run-20261019-200423
    python scripts/run_pipeline.py --projections PA,RLAT             # chest PA and right lateral only
    python scripts/run_pipeline.py --isaac-root /opt/isaac-sim       # another Isaac Sim install
    python scripts/run_pipeline.py --set sequence.idle_s.outside=4   # any config value
    python scripts/run_pipeline.py --dry-run                         # resolve inputs + print the visit plan only

Every run creates output/sdg/run-<timestamp>/; every human becomes SD.<n>/ in it with <EXAM>/timeline.txt (time-stamped patient actions).
Exit codes: 0 ok, 1 Isaac / animation error, 2 configuration or input error.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_xray.config import ConfigError, load_config, parse_set_args  # noqa: E402
from sdg_xray.logging_setup import setup_logging  # noqa: E402
from sdg_xray.paths import CONFIG_DIR  # noqa: E402
from sdg_xray.pipeline import run_pipeline  # noqa: E402


def _ids(text):
    return [t.strip() for t in text.split(",") if t.strip()] if text else None


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(CONFIG_DIR), help="config directory (default: sdg/configs)")
    parser.add_argument("--humans", type=int, help="number of humans (run.humans.count)")
    parser.add_argument("--rooms", type=int, help="number of rooms (run.rooms.count)")
    parser.add_argument("--human-ids", help="comma-separated human ids, e.g. H0001,H0007")
    parser.add_argument("--room-ids", help="comma-separated room ids, e.g. R0001")
    parser.add_argument("--humans-root", help="humans run dir or folder of runs (default: latest in output/humans)")
    parser.add_argument("--rooms-root", help="rooms run dir or folder of runs (default: latest in output/rooms)")
    parser.add_argument("--exam", default=None, help="exam name in run.exams to run (default: all), e.g. CHEST")
    parser.add_argument("--projections", help="comma-separated projections for --exam (default: as configured)")
    parser.add_argument("--output-root", help="folder for the run-<timestamp> folders (default: output/sdg)")
    parser.add_argument("--isaac-root", help="Isaac Sim install folder (isaac.root)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--headless", action="store_true", help="run Isaac Sim without a window")
    mode.add_argument("--gui", action="store_true", help="run Isaac Sim with a window (default unless isaac.headless)")
    parser.add_argument("--no-capture", action="store_true", help="animate only, no image capture (capture.enabled)")
    parser.add_argument("--no-overlay", action="store_true",
                        help="do not draw the annotations into the RGB images (annotations.overlay.enabled)")
    parser.add_argument("--keep-open", action="store_true", help="GUI: keep Isaac Sim open after the last visit")
    parser.add_argument("--set", action="append", metavar="KEY=VALUE", default=[],
                        help="override any config value, e.g. --set poses.timing.fov_on_s=2 (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="resolve inputs and print the visit plan, no Isaac Sim")
    parser.add_argument("-v", "--verbose", action="store_true", help="also show Isaac Sim's own console output")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging()
    try:
        overrides = parse_set_args(args.set)
        overrides.update({
            "run.humans.count": args.humans, "run.rooms.count": args.rooms,
            "run.humans.ids": _ids(args.human_ids), "run.rooms.ids": _ids(args.room_ids),
            "run.humans.root": args.humans_root, "run.rooms.root": args.rooms_root,
            "run.output_root": args.output_root, "isaac.root": args.isaac_root,
            "isaac.headless": True if args.headless else (False if args.gui else None),
            "isaac.keep_open": True if args.keep_open else None,
            "capture.enabled": False if args.no_capture else None,
            "annotations.overlay.enabled": False if args.no_overlay else None,
        })
        cfg = load_config(args.config, overrides)
        exams = cfg["run"]["exams"]
        if args.exam:
            if args.exam not in exams and not args.projections:
                raise ConfigError(f"--exam {args.exam}: not in run.exams ({', '.join(exams)}); give --projections too")
            exams = {args.exam: exams.get(args.exam)}
        if args.projections:
            if len(exams) != 1:
                raise ConfigError("--projections needs a single exam (use --exam when run.exams has several)")
            exams = {next(iter(exams)): _ids(args.projections)}
        if exams != cfg["run"]["exams"]:
            cfg = load_config(args.config, dict(overrides, **{"run.exams": exams}))
    except ConfigError as exc:
        print(f"[ERROR] [config] {exc}")
        return 2
    return run_pipeline(cfg, dry_run=args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
