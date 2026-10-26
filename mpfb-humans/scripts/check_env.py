#!/usr/bin/env python3
"""Run the preflight environment checks only (no run directory is created).

    python scripts/check_env.py [--config configs] [--fix] [--install-packs]

--fix generates missing gown assets; --install-packs downloads + installs missing asset packs.
--setup does both (complete one-time setup of a new machine).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from make_gown import generate as generate_gowns  # noqa: E402

from sdg_humans import preflight  # noqa: E402
from sdg_humans.config import ConfigError, load_config  # noqa: E402
from sdg_humans.logging_setup import setup_console_only  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs")
    parser.add_argument("--fix", action="store_true", help="generate missing gown assets")
    parser.add_argument("--install-packs", action="store_true", help="download + install missing asset packs")
    parser.add_argument("--setup", action="store_true", help="--fix and --install-packs")
    args = parser.parse_args()
    setup_console_only()
    try:
        cfg = load_config(args.config)
        print("[config]    OK   all YAML files valid")
    except ConfigError as exc:
        print(f"[config]    FAIL {exc}")
        return 2
    checks = preflight.run_preflight(cfg, auto_fix=args.fix or args.setup, gown_generator=generate_gowns,
                                     install_packs=args.install_packs or args.setup)
    ok = preflight.report(checks)
    print("[preflight] PASSED" if ok else "[preflight] FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
