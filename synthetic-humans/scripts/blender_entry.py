"""Single entry point for code running inside Blender.

    blender -b -P scripts/blender_entry.py -- <task> <args.json> <result.json> [<log_file>]

Tasks: build (one human), gown (gown assets), calibrate (landmark anchors), probe (environment).
The result JSON always gets {"status": ...}; on errors also "error" and "traceback".
"""

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans.logging_setup import setup_worker_logging  # noqa: E402


def _task(name):
    if name == "build":
        from sdg_humans.blender.pipeline import run
    elif name == "gown":
        from sdg_humans.blender.gown.run import run
    elif name == "calibrate":
        from sdg_humans.blender.calibrate import run
    elif name == "probe":
        from sdg_humans.blender.probe import run
    else:
        raise ValueError(f"unknown task {name}")
    return run


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:]
    task, args_path, result_path = argv[0], Path(argv[1]), Path(argv[2])
    log_file = argv[3] if len(argv) > 3 else str(result_path.with_suffix(".log"))
    args = json.loads(args_path.read_text(encoding="utf-8"))
    log = setup_worker_logging(log_file, args.get("log_level", "INFO"), args.get("log_format"))
    started = time.monotonic()
    try:
        result = _task(task)(args)
    except Exception as exc:  # noqa: BLE001 - report every failure to the orchestrator
        log.error(f"task {task} failed: {exc}\n{traceback.format_exc()}")
        result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
    result["duration_s"] = round(time.monotonic() - started, 2)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return 0 if result.get("status") in ("ok", "warn") else 1


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    import bpy  # noqa: E402
    bpy.ops.wm.quit_blender() if code == 0 else sys.exit(code)
