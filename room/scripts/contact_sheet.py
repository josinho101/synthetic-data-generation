#!/usr/bin/env python3
"""Rebuild <run>/contact_sheet.png from the rooms' floor plans.

    python scripts/contact_sheet.py <output_root>/run-... [--columns 4]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_room.metadata.report import contact_sheet  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir")
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args(argv)
    run = Path(args.run_dir)
    ids = sorted(p.name for p in (run / "rooms").iterdir() if p.is_dir())
    ok = contact_sheet(run, ids, run / "contact_sheet.png", args.columns)
    print(f"{'wrote' if ok else 'no plans found for'} {run / 'contact_sheet.png'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
