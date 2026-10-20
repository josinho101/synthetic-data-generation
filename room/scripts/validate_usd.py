#!/usr/bin/env python3
"""Re-validate room USDs: a run directory (all rooms) or single .usd files.

    python scripts/validate_usd.py <output_root>/run-...
    python scripts/validate_usd.py <output_root>/run-.../rooms/R0001/R0001.usd
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_room.pipeline.validate import validate_usd  # noqa: E402


def _targets(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from sorted(p.glob("rooms/*/*.usd*"))
        else:
            yield p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    failed = 0
    for usd in _targets(argv):
        meta_path = usd.with_suffix(".json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        room = meta.get("room", {})
        res = validate_usd(usd, room.get("footprint_m"), room.get("ceiling_height_m"), cameras=meta.get("cameras"))
        failed += res["status"] == "failed"
        print(f"{res['status'].upper():6} {usd}  meshes={res.get('meshes')} lights={res.get('lights')} "
              f"bounds={res.get('bounds')}")
        for e in res["errors"]:
            print(f"   ERROR {e}")
        for w in res["warnings"]:
            print(f"   WARN  {w}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
