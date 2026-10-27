#!/usr/bin/env python3
"""Stage 1 only: sample the population and print / write the manifest (no body model needed).

    python scripts/sample_population.py --dry-run           # print the stratification table
    python scripts/sample_population.py --out manifest.json # write a manifest file
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anny_humans.config import ConfigError, load_config  # noqa: E402
from anny_humans.logging_setup import setup_console_only  # noqa: E402
from anny_humans.sampling.face import load_target_catalogue  # noqa: E402
from anny_humans.sampling.manifest import build_specs, write_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs"))
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--age-min", type=int, help="override population.age_range.min (>= 18)")
    parser.add_argument("--age-max", type=int, help="override population.age_range.max (<= 70)")
    parser.add_argument("--out", help="write manifest JSON here")
    parser.add_argument("--dry-run", action="store_true", help="only print the tables")
    args = parser.parse_args()
    setup_console_only()
    try:
        cfg = load_config(args.config, {"population.count": args.count, "population.seed": args.seed,
                                        "population.age_range.min": args.age_min,
                                        "population.age_range.max": args.age_max})
    except ConfigError as exc:
        print(f"[config] {exc}")
        return 2
    specs = build_specs(cfg, load_target_catalogue())
    n = len(specs)
    for key in ("sex", "ethnicity", "age_band", "somatotype", "clothing_variant"):
        print(f"{key}:")
        for label, count in sorted(Counter(s[key] for s in specs).items()):
            print(f"  {label:<22} {count:>4}  ({100.0 * count / n:5.1f}%)")
    print("sex x ethnicity:")
    for (sex, eth), count in sorted(Counter((s["sex"], s["ethnicity"]) for s in specs).items()):
        print(f"  {sex:<7} {eth:<18} {count:>4}")
    ages = [s["age_years"] for s in specs]
    print(f"age years: min {min(ages)} mean {sum(ages) / n:.1f} max {max(ages)}")
    heights = [s["target_height_cm"] for s in specs]
    print(f"target height cm: min {min(heights)} mean {sum(heights) / n:.1f} max {max(heights)}")
    distances = [s["uniqueness_distance"] for s in specs if s["uniqueness_distance"] is not None]
    if distances:
        print(f"identity distance to nearest earlier human: min {min(distances):.3f} mean {sum(distances) / len(distances):.3f}")
    if args.out and not args.dry_run:
        write_manifest(args.out, "standalone", cfg, specs)
        print(f"manifest written to {args.out}")
    elif not args.dry_run:
        print(json.dumps(specs[0], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
