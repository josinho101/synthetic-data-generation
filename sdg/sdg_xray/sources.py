"""Find the humans / rooms to use: a configured run, or the latest run of the humans / rooms pipelines."""

import json
import logging
from pathlib import Path

from .config import ConfigError

log = logging.getLogger(__name__)

KINDS = {"humans": "humans", "rooms": "rooms"}   # kind -> items folder inside a run


def _ok_ids(run_dir: Path) -> list:
    """Ids with status ok/warn in results.json, in manifest order (or folder order without a manifest)."""
    results = run_dir / "results.json"
    if not results.exists():
        return []
    data = json.loads(results.read_text())          # {id: {status, usd, ...}} (humans and rooms pipelines)
    if not isinstance(data, dict):
        return []
    return sorted(k for k, v in data.items() if isinstance(v, dict) and v.get("status") in ("ok", "warn"))


def is_run_dir(path: Path, kind: str) -> bool:
    return (path / KINDS[kind]).is_dir() and (path / "results.json").exists()


def resolve_run(root, kind: str, default_root: Path) -> Path:
    """`root` may be a run dir or a folder of run-* dirs (None -> default_root). Returns the run dir to use:
    the root itself, or its newest run-* (by name = timestamp) that has at least one ok/warn item."""
    root = Path(root) if root else Path(default_root)
    if not root.exists():
        raise ConfigError(f"{kind} root not found: {root}")
    if is_run_dir(root, kind):
        return root
    for run in sorted((p for p in root.glob("run-*") if p.is_dir()), reverse=True):
        if is_run_dir(run, kind) and _ok_ids(run):
            return run
        log.debug("skip %s (no finished %s)", run, kind)
    raise ConfigError(f"no finished {kind} run in {root} (expected run-*/{KINDS[kind]}/ with results.json)")


def select_items(run_dir: Path, kind: str, count=None, ids=None) -> list:
    """[{id, usd, json, run}] for the first `count` ok items of the run, or exactly `ids`."""
    available = _ok_ids(run_dir)
    if ids:
        missing = [i for i in ids if i not in available]
        if missing:
            raise ConfigError(f"{kind} {', '.join(missing)} not found (or not ok) in {run_dir}; "
                              f"available: {', '.join(available[:12])}{' ...' if len(available) > 12 else ''}")
        chosen = list(ids)
    else:
        if len(available) < count:
            raise ConfigError(f"{count} {kind} requested but {run_dir} has only {len(available)} finished")
        chosen = available[:count]
    items = []
    for item_id in chosen:
        folder = run_dir / KINDS[kind] / item_id
        usd = next((folder / f"{item_id}.{ext}" for ext in ("usd", "usda", "usdc") if (folder / f"{item_id}.{ext}").exists()),
                   None)
        meta = folder / f"{item_id}.json"
        if usd is None or not meta.exists():
            raise ConfigError(f"{kind[:-1]} {item_id}: USD or metadata JSON missing in {folder}")
        items.append({"id": item_id, "usd": str(usd), "json": str(meta), "run": str(run_dir)})
    return items
