#!/usr/bin/env python3
"""Environment + configuration check (Python, packages, output folder, config validation, one test layout)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_room.config import ConfigError, load_config  # noqa: E402
from sdg_room.config.schema import footprint_m, max_sid  # noqa: E402
from sdg_room.paths import CONFIG_DIR  # noqa: E402
from sdg_room.pipeline.orchestrator import preflight  # noqa: E402
from sdg_room.sampling.manifest import build_room_spec  # noqa: E402


def main() -> int:
    try:
        cfg = load_config(CONFIG_DIR)
    except ConfigError as exc:
        print(f"FAIL config\n{exc}")
        return 2
    print("OK   config            all files valid")
    problems = preflight(cfg)
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        from pxr import Usd
        print(f"OK   python/packages   Python {sys.version.split()[0]}, usd-core {'.'.join(map(str, Usd.GetVersion()))}")
        print(f"OK   output_root       {cfg['export']['output_root']}")
    L, W = footprint_m(cfg["room"])
    print(f"OK   footprint         {L:.3f} x {W:.3f} m, max SID {max_sid(cfg['equipment'], W):.2f} m")
    try:
        spec = build_room_spec(cfg, 0)
        print(f"OK   layout            first room solved after {spec['attempt'] + 1} attempt(s)")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL layout           {exc}")
        problems.append(str(exc))
    print("[preflight] PASSED" if not problems else "[preflight] FAILED")
    return 0 if not problems else 2


if __name__ == "__main__":
    sys.exit(main())
