#!/usr/bin/env python3
"""Pose a generated human into the X-ray exam poses, apply coupled anatomical motion, check the range of motion.

    .venv/bin/python scripts/pose_exams.py <run>/humans/H0001/H0001.usd       # -> H0001_exam_poses.usda + .json
    .venv/bin/python scripts/pose_exams.py H0001.usd --poses chest_pa chest_lateral --out poses.usda

Poses (sdg_humans/pose_rules.py, identical for the MHR pipeline): neutral, chest_pa (hands on hips,
shoulders forward, full inspiration), chest_lateral (arms overhead, full inspiration), spine_ap,
spine_lateral (arms forward), trunk_flexion_30, invalid_test (hyperextended elbow / knee: must be flagged).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from sdg_humans import pose_rules, pose_usd  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("human_usd")
    parser.add_argument("--config", default=str(ROOT / "configs" / "poses.yaml"))
    parser.add_argument("--poses", nargs="+", choices=list(pose_rules.EXAM_POSES))
    parser.add_argument("--out")
    args = parser.parse_args()
    human = Path(args.human_usd).resolve()
    out = Path(args.out) if args.out else human.with_name(f"{human.stem}_exam_poses.usda")
    report = pose_usd.run(human, yaml.safe_load(Path(args.config).read_text()), out, args.poses)
    for p in report["poses"]:
        flags = ", ".join(f"{v['angle']}={v['value']:.0f}" for v in p["violations"]) or "ok"
        print(f"  {p['name']:<18} {flags}")
    print(f"[poses] {len(report['poses'])} poses -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
