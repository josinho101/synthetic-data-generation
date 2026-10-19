"""Load all YAML config files into one dict and validate it."""

import copy
import os
from pathlib import Path

from ..paths import CONFIG_FILES
from .schema import validate


class ConfigError(ValueError):
    """Raised when the configuration is missing or invalid."""

    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("Invalid configuration:\n  - " + "\n  - ".join(self.errors))


def _read_yaml(path: Path) -> dict:
    import yaml  # system Python only; never imported inside Blender

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError([f"{path.name}: top level must be a mapping"])
    return data


def _expand_paths(cfg: dict) -> None:
    export = cfg.get("export", {})
    for key in ("output_root", "blender_bin", "mpfb_data_dir"):
        value = export.get(key)
        if isinstance(value, str) and value != "auto":
            export[key] = os.path.expandvars(os.path.expanduser(value))


def apply_overrides(cfg: dict, overrides: dict) -> dict:
    """Apply dotted-key overrides, e.g. {"population.count": 1, "export.workers": 2}."""
    cfg = copy.deepcopy(cfg)
    for dotted, value in (overrides or {}).items():
        if value is None:
            continue
        node = cfg
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return cfg


def load_config(config_dir, overrides=None, validate_config=True) -> dict:
    """Return {"population": {...}, "appearance": {...}, ...} for the given directory."""
    config_dir = Path(config_dir)
    missing = [f"{name}.yaml" for name in CONFIG_FILES if not (config_dir / f"{name}.yaml").exists()]
    if missing:
        raise ConfigError([f"missing config file {config_dir / m}" for m in missing])

    cfg = {name: _read_yaml(config_dir / f"{name}.yaml") for name in CONFIG_FILES}
    cfg = apply_overrides(cfg, overrides)
    _expand_paths(cfg)
    cfg["_config_dir"] = str(config_dir.resolve())

    if validate_config:
        errors = validate(cfg)
        if errors:
            raise ConfigError(errors)
    return cfg
