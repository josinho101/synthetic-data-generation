#!/usr/bin/env python3
"""Sample room specs + layouts without building USD (fast check of the configuration).

    python scripts/sample_rooms.py --dry-run                     # distribution tables only
    python scripts/sample_rooms.py --plans /tmp/plans            # also write <id>_plan.png floor plans
    python scripts/sample_rooms.py --out manifest.json --count 20
"""

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_room.config import ConfigError, load_config, parse_set_args  # noqa: E402
from sdg_room.logging_setup import setup_console_only  # noqa: E402
from sdg_room.metadata.report import CATEGORICAL, contact_sheet  # noqa: E402
from sdg_room.paths import CONFIG_DIR  # noqa: E402
from sdg_room.preview.plan_png import render_plan  # noqa: E402
from sdg_room.progress import describe, print_distribution_table  # noqa: E402
from sdg_room.sampling.manifest import build_specs, write_manifest  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(CONFIG_DIR))
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--dry-run", action="store_true", help="print only, write nothing")
    parser.add_argument("--out", help="write the manifest JSON here")
    parser.add_argument("--plans", help="write floor-plan PNGs (+ contact_sheet.png) into this directory")
    args = parser.parse_args(argv)
    setup_console_only()
    log = logging.getLogger("sample_rooms")
    try:
        overrides = parse_set_args(args.set)
        overrides.update({"variations.count": args.count, "variations.seed": args.seed})
        cfg = load_config(args.config, overrides)
    except ConfigError as exc:
        print(f"[config] {exc}")
        return 2
    specs = build_specs(cfg)
    for spec in specs:
        lay = spec["layout"]
        extra = f" | dropped {lay['dropped']}" if lay.get("dropped") else ""
        log.info(f"{describe(spec)} | rejections {len(spec['layout_rejections'])}{extra}")
    for key in CATEGORICAL:
        print_distribution_table(key, cfg["variations"][key], Counter(s[key] for s in specs), len(specs))
    if args.dry_run:
        return 0
    if args.out:
        write_manifest(args.out, specs, {"seed": cfg["variations"]["seed"]})
        log.info(f"manifest -> {args.out}")
    if args.plans:
        out = Path(args.plans)
        for spec in specs:
            (out / "rooms" / spec["id"]).mkdir(parents=True, exist_ok=True)
            render_plan(spec, out / "rooms" / spec["id"] / f"{spec['id']}_plan.png",
                        cfg["export"]["preview"]["plan_px_per_m"], cfg["room"]["wall_thickness_m"])
        contact_sheet(out, [s["id"] for s in specs], out / "contact_sheet.png",
                      cfg["export"]["preview"]["contact_sheet_columns"])
        log.info(f"floor plans -> {out}/rooms/<id>/<id>_plan.png, {out}/contact_sheet.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
