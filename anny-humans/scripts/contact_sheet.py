#!/usr/bin/env python3
"""(Re)build the contact sheet (grid of preview PNGs) of a run.

    python scripts/contact_sheet.py <run dir> [--columns 8]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anny_humans.metadata.report import write_contact_sheet  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir")
    parser.add_argument("--columns", type=int, default=8)
    args = parser.parse_args()
    run = Path(args.run_dir)
    ids = sorted(p.name for p in (run / "humans").iterdir() if p.is_dir())
    out = run / "contact_sheet.png"
    ok = write_contact_sheet(out, run / "humans", ids, args.columns)
    print(f"contact sheet -> {out}" if ok else "no previews found")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
