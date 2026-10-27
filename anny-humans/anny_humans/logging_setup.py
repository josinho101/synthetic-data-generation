"""Logging set-up for the orchestrator (dictConfig) and per-human log files (stdlib only)."""

import copy
import logging
import logging.config
import sys
import threading
from contextlib import contextmanager
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
    copy anny-humans/logs/<run_id>.log; only the newest `keep_last_runs` central
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


class _ThreadFilter(logging.Filter):
    """Pass only records logged by one thread (one human is built per worker thread)."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record) -> bool:
        return record.thread == self.thread_id


@contextmanager
def human_log(log_file, level="INFO", fmt=None):
    """While active, records of the calling thread also go to <run>/logs/humans/<id>.log at `level`."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    handler.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    handler.setFormatter(logging.Formatter(fmt or "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"))
    handler.addFilter(_ThreadFilter(threading.get_ident()))
    root = logging.getLogger()
    if handler.level < root.level:
        root.setLevel(handler.level)
    root.addHandler(handler)
    try:
        yield log_file
    finally:
        root.removeHandler(handler)
        handler.close()
