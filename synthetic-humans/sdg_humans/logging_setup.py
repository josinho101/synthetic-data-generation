"""Logging set-up for the orchestrator (dictConfig) and for Blender workers (stdlib only)."""

import copy
import logging
import logging.config
import sys
from pathlib import Path

from .paths import CENTRAL_LOG_DIR


def _substitute(node, run_dir: str):
    if isinstance(node, dict):
        return {k: _substitute(v, run_dir) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, run_dir) for v in node]
    if isinstance(node, str):
        return node.replace("{run_dir}", run_dir)
    return node


def _prune_central_logs(keep_last: int) -> None:
    logs = sorted(CENTRAL_LOG_DIR.glob("run-*.log"), key=lambda p: p.stat().st_mtime)
    for old in logs[:-keep_last] if keep_last > 0 else logs:
        try:
            old.unlink()
        except OSError:
            pass


def setup_run_logging(logging_cfg: dict, run_dir: Path, run_id: str) -> Path:
    """Configure root logging for one pipeline run. Returns the central log file path.

    Files: <run>/logs/pipeline.log (run_file level, INFO by default), <run>/logs/errors.log (ERROR) and a central
    copy synthetic-humans/logs/<run_id>.log; only the newest `keep_last_runs` central
    logs are kept, so the logs rotate per run.
    """
    run_dir = Path(run_dir)
    (run_dir / "logs" / "humans").mkdir(parents=True, exist_ok=True)
    CENTRAL_LOG_DIR.mkdir(parents=True, exist_ok=True)

    dict_cfg = _substitute(copy.deepcopy(logging_cfg["dict_config"]), str(run_dir))
    logging.config.dictConfig(dict_cfg)

    central = CENTRAL_LOG_DIR / f"{run_id}.log"
    handler = logging.FileHandler(central, encoding="utf-8")
    file_level = dict_cfg.get("handlers", {}).get("run_file", {}).get("level", "INFO")
    handler.setLevel(getattr(logging, str(file_level).upper(), logging.INFO))
    detailed = dict_cfg.get("formatters", {}).get("detailed", {}).get("format")
    handler.setFormatter(logging.Formatter(detailed or "%(asctime)s | %(levelname)s | %(message)s"))
    logging.getLogger().addHandler(handler)

    _prune_central_logs(int(logging_cfg.get("keep_last_runs", 20)))
    return central


def setup_console_only(level=logging.INFO) -> None:
    """Minimal logging for helper scripts that run without a run directory."""
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stdout, force=True)


def setup_worker_logging(log_file, level="INFO", fmt=None) -> logging.Logger:
    """Logging inside a Blender worker: `level` (default INFO) to the per-human file, INFO to stdout."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt or "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    file_level = getattr(logging, str(level).upper(), logging.INFO)
    root.setLevel(min(file_level, logging.INFO))

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("[worker] %(levelname)s %(name)s: %(message)s"))
    root.addHandler(console)
    return logging.getLogger("sdg_humans.worker")
