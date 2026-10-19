"""Run directory handling: one new timestamped directory per pipeline run."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RunContext:
    run_id: str
    run_dir: Path

    @property
    def humans_dir(self) -> Path:
        return self.run_dir / "humans"

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def resolved_config_path(self) -> Path:
        return self.run_dir / "resolved_config.json"

    def human_dir(self, human_id: str) -> Path:
        return self.humans_dir / human_id

    def human_log(self, human_id: str) -> Path:
        return self.logs_dir / "humans" / f"{human_id}.log"


def create_run(output_root, run_dir_format="run-%Y%m%d-%H%M%S") -> RunContext:
    """Create <output_root>/run-<timestamp>/ (adds a suffix if the name already exists)."""
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    base = datetime.now().strftime(run_dir_format)
    run_dir, suffix = root / base, 1
    while run_dir.exists():
        suffix += 1
        run_dir = root / f"{base}-{suffix}"
    for sub in ("humans", "logs/humans", "config_snapshot"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    return RunContext(run_id=run_dir.name, run_dir=run_dir)


def open_run(run_dir) -> RunContext:
    """Re-open an existing run directory (for --resume / --only)."""
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "manifest.json").exists():
        raise FileNotFoundError(f"{run_dir} is not a run directory (no manifest.json)")
    return RunContext(run_id=run_dir.name, run_dir=run_dir)


def snapshot_config(ctx: RunContext, cfg: dict, config_dir) -> None:
    """Copy the YAML files and write the fully resolved config as JSON (read by Blender)."""
    for path in Path(config_dir).glob("*.yaml"):
        shutil.copy2(path, ctx.run_dir / "config_snapshot" / path.name)
    with open(ctx.resolved_config_path, "w", encoding="utf-8") as handle:
        json.dump(cfg, handle, indent=2, default=str)
