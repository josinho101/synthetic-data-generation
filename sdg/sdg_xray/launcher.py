"""Start Isaac Sim (python.sh + isaac/run_exam.py) with a job file, stream its console, return its exit code."""

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from .config import ConfigError
from .paths import ISAAC_SCRIPT

log = logging.getLogger(__name__)

PREFIX = "[xray]"          # lines printed by run_exam.py; everything else is Isaac's own output


def isaac_python(isaac_cfg: dict) -> Path:
    root = Path(isaac_cfg["root"])
    exe = root / isaac_cfg.get("python", "python.sh")
    if not root.is_dir():
        raise ConfigError(f"Isaac Sim not found: {root} (set isaac.root in configs/isaac.yaml or --isaac-root)")
    if not exe.exists():
        raise ConfigError(f"Isaac Sim launcher not found: {exe}")
    return exe


def isaac_version(isaac_cfg: dict) -> str:
    version = Path(isaac_cfg["root"]) / "VERSION"
    return version.read_text().strip() if version.exists() else "unknown"


def run_isaac(job_file: Path, isaac_cfg: dict, verbose: bool = False) -> int:
    """Run the job in Isaac Sim. Lines from run_exam.py go to the log; Isaac's own lines only with --verbose
    (errors and tracebacks are always shown)."""
    exe = isaac_python(isaac_cfg)
    cmd = [str(exe), str(ISAAC_SCRIPT), "--job", str(job_file)]
    log.info("Starting Isaac Sim %s (%s mode): %s", isaac_version(isaac_cfg),
             "headless" if isaac_cfg.get("headless") else "GUI", " ".join(cmd))
    timeout = float(isaac_cfg.get("run_timeout_s", 3600))
    start = time.time()
    proc = subprocess.Popen(cmd, cwd=str(exe.parent), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, start_new_session=True, env=dict(os.environ, PYTHONUNBUFFERED="1"))
    in_traceback, errors = False, 0
    try:
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if line.startswith(PREFIX):
                text = line[len(PREFIX):].strip()
                errors += text.startswith("[ERROR]")
                (log.error if text.startswith("[ERROR]") else log.info)(text)
                in_traceback = False
            elif line.startswith("Traceback") or in_traceback:
                in_traceback = bool(line.strip())
                log.error("  isaac | %s", line)
            elif verbose or "[Error]" in line:
                log.info("  isaac | %s", line)
            if time.time() - start > timeout:
                raise TimeoutError
        code = proc.wait()
    except TimeoutError:
        log.error("[ERROR] Isaac run exceeded isaac.run_timeout_s = %.0f s, terminating", timeout)
        os.killpg(proc.pid, signal.SIGTERM)
        code = 124
    except KeyboardInterrupt:
        log.error("[ERROR] interrupted, terminating Isaac Sim")
        os.killpg(proc.pid, signal.SIGTERM)
        code = 130
    log.info("Isaac Sim exited with code %s after %.0f s", code, time.time() - start)
    if code == 0 and errors:        # SimulationApp.close() can end the process with 0 before sys.exit(1) runs
        code = 1
    return code
