#!/usr/bin/env python3
"""Run the preflight environment checks only (no run directory is created).

    python scripts/check_env.py [--config configs]

The MakeHuman asset packs are shared with the MPFB pipeline; install them with
mpfb-humans/scripts/install_asset_packs.py (or the MPFB check_env.py --install-packs).
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anny_humans import preflight  # noqa: E402
from anny_humans.config import ConfigError, load_config  # noqa: E402
from anny_humans.logging_setup import setup_console_only  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default=str(ROOT / "configs"))
    args = parser.parse_args()
    setup_console_only()
    try:
        cfg = load_config(args.config)
        print("[config]    OK   all YAML files valid")
    except ConfigError as exc:
        print(f"[config]    FAIL {exc}")
        return 2
    ok = preflight.report(preflight.run_preflight(cfg))
    print("[preflight] PASSED" if ok else "[preflight] FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
