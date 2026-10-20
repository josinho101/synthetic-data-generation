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
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError([f"{path.name}: top level must be a mapping"])
    return data


def _expand_paths(cfg: dict) -> None:
    export = cfg.get("export", {})
    value = export.get("output_root")
    if isinstance(value, str):
        export["output_root"] = os.path.expandvars(os.path.expanduser(value))


NULL = object()   # override value that really sets None (plain None means "not given")


def apply_overrides(cfg: dict, overrides: dict) -> dict:
    """Apply dotted-key overrides, e.g. {"variations.count": 1, "room.footprint_ft": [20, 10]}.
    None values are skipped (unset CLI flags); use NULL to set a key to null."""
    cfg = copy.deepcopy(cfg)
    for dotted, value in (overrides or {}).items():
        if value is None:
            continue
        if value is NULL:
            value = None
        node = cfg
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return cfg


def parse_set_args(items) -> dict:
    """['room.footprint_ft=[20,10]', 'export.workers=1'] -> {dotted key: YAML-parsed value}."""
    import yaml

    overrides = {}
    for item in items or []:
        if "=" not in item:
            raise ConfigError([f"--set {item!r}: expected key=value"])
        key, raw = item.split("=", 1)
        value = yaml.safe_load(raw)
        overrides[key.strip()] = NULL if value is None else value
    return overrides


def load_config(config_dir, overrides=None, validate_config=True) -> dict:
    """Return {"variations": {...}, "room": {...}, ...} for the given directory."""
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
