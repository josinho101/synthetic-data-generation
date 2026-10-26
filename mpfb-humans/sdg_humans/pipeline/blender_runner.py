"""Run one Blender task in a headless subprocess and collect its JSON result."""

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from ..paths import SCRIPTS_DIR

_LOG = logging.getLogger("sdg_humans.blender_runner")
ENTRY = SCRIPTS_DIR / "blender_entry.py"


def run_task(blender_bin: str, task: str, args: dict, log_file, timeout_s: int = 1800, work_dir=None) -> dict:
    """blender -b -P blender_entry.py -- task args.json result.json log_file  ->  result dict.

    Blender's own stdout/stderr is appended to log_file as well, so one file holds the
    complete story of the task.
    """
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir or tempfile.mkdtemp(prefix=f"sdg_{task}_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    args_path, result_path = work_dir / f"{task}_args.json", work_dir / f"{task}_result.json"
    args_path.write_text(json.dumps(args, indent=2, default=str), encoding="utf-8")
    if result_path.exists():
        result_path.unlink()
    cmd = [blender_bin, "-b", "--python-exit-code", "1", "-P", str(ENTRY), "--",
           task, str(args_path), str(result_path), str(log_file)]
    _LOG.debug(f"running: {' '.join(cmd)}")
    try:
        with open(log_file.with_suffix(".blender.log"), "a", encoding="utf-8") as out:
            proc = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, timeout=timeout_s, check=False)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        return {"status": "failed", "error": f"timeout after {timeout_s}s", "log": str(log_file)}
    if not result_path.exists():
        return {"status": "failed", "error": f"Blender exited with code {code} without a result",
                "log": str(log_file)}
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.setdefault("log", str(log_file))
    return result
