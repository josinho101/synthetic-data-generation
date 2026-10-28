"""Load all YAML config files into one dict and validate it (same --set pattern as room/ and mpfb-humans/)."""

import copy
import os
from pathlib import Path

from .paths import CONFIG_FILES

FACINGS = ("detector", "left", "right", "tube")


class ConfigError(ValueError):
    """Raised when the configuration or the inputs are missing or invalid."""

    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("\n  - ".join(["Invalid configuration:"] + self.errors) if len(self.errors) > 1
                         else self.errors[0])


NULL = object()   # override value that really sets None (plain None means "not given")


def _read_yaml(path: Path) -> dict:
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: top level must be a mapping")
    return data


def apply_overrides(cfg: dict, overrides: dict) -> dict:
    """Apply dotted-key overrides, e.g. {"run.humans.count": 1}. None values are skipped; NULL sets None."""
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
    """['run.humans.count=3', 'isaac.headless=true'] -> {dotted key: YAML-parsed value}."""
    import yaml

    overrides = {}
    for item in items or []:
        if "=" not in item:
            raise ConfigError(f"--set {item!r}: expected key=value")
        key, raw = item.split("=", 1)
        value = yaml.safe_load(raw)
        overrides[key.strip()] = NULL if value is None else value
    return overrides


def _expand(value):
    return os.path.expandvars(os.path.expanduser(value)) if isinstance(value, str) else value


def validate(cfg: dict) -> list:
    errors = []
    run, poses, isaac = cfg["run"], cfg["poses"], cfg["isaac"]
    for kind in ("humans", "rooms"):
        sel = run.get(kind) or {}
        ids, count = sel.get("ids"), sel.get("count")
        if ids is not None and (not isinstance(ids, list) or not ids):
            errors.append(f"run.{kind}.ids must be a non-empty list or null")
        if ids is None and (not isinstance(count, int) or count < 1):
            errors.append(f"run.{kind}.count must be an integer >= 1")
    exams = run.get("exams") or {}
    if not isinstance(exams, dict) or not exams:
        errors.append("run.exams must map an exam name (e.g. CHEST) to a list of projections")
    projections = poses.get("projections") or {}
    arm_poses = poses.get("arm_poses") or {}
    for exam, names in (exams.items() if isinstance(exams, dict) else []):
        if not isinstance(names, list) or not names:
            errors.append(f"run.exams.{exam} must be a non-empty list of projections")
            continue
        for name in names:
            if name not in projections:
                errors.append(f"run.exams.{exam}: projection {name!r} is not defined in poses.yaml")
    for name, proj in projections.items():
        if proj.get("facing") not in FACINGS:
            errors.append(f"poses.projections.{name}.facing must be one of {FACINGS}")
        if proj.get("arms") not in arm_poses:
            errors.append(f"poses.projections.{name}.arms {proj.get('arms')!r} is not in poses.arm_poses")
    for name, pose in arm_poses.items():
        pose = pose or {}
        if not pose.get("anchor"):
            errors.append(f"poses.arm_poses.{name}.anchor (motion library joint, e.g. Head / Pelvis) is required")
        if not pose.get("left") and not pose.get("right"):
            errors.append(f"poses.arm_poses.{name} needs left (and optionally right)")
        for side in ("left", "right", "via", "via_right"):
            hand = pose.get(side)
            if hand is None:
                continue
            for key in ("wrist_cm", "elbow", "fingers", "palm"):
                value = hand.get(key)
                if value is None and key != "wrist_cm":
                    continue
                if not isinstance(value, list) or len(value) != 3 or not all(isinstance(v, (int, float)) for v in value):
                    errors.append(f"poses.arm_poses.{name}.{side}.{key} must be [x, y, z]")
    for key, value in (poses.get("timing") or {}).items():
        if not isinstance(value, (int, float)) or value < 0:
            errors.append(f"poses.timing.{key} must be a number >= 0")
    if not isaac.get("root"):
        errors.append("isaac.root (Isaac Sim install folder) is required")
    if cfg["capture"].get("enabled"):
        from .capture import validate_capture
        errors += validate_capture(cfg["capture"], float(isaac.get("fps", 30)))
    maps = isaac.get("retarget_maps") or {}
    if not isinstance(maps, dict) or "default" not in maps:
        errors.append("isaac.retarget_maps must map rig ids (<id>.json skeleton.rig) to retarget configs, with a default")
        maps = {}
    for rig, name in maps.items():
        if not str(name).startswith("retarget_") or name not in cfg:
            errors.append(f"isaac.retarget_maps.{rig}: {name!r} is not a loaded retarget_*.yaml config")
    for name in sorted(k for k in cfg if k.startswith("retarget_")):
        retarget = cfg[name]
        if not (retarget.get("tags") or {}):
            errors.append(f"{name}.tags is empty")
        if str(retarget.get("root_joint_name", "SkelOrigin")).lower() == "root":
            errors.append(f"{name}.root_joint_name must differ from MPFB's 'root' (case-insensitive)")
    from .annotations import validate_annotations
    errors += validate_annotations(cfg["annotations"])
    return errors


def load_config(config_dir, overrides=None) -> dict:
    """Return {"run": {...}, "sequence": {...}, "poses": {...}, "isaac": {...}, "retarget_mpfb": {...}, ...}: one entry
    per file of CONFIG_FILES."""
    config_dir = Path(config_dir)
    missing = [f"{name}.yaml" for name in CONFIG_FILES if not (config_dir / f"{name}.yaml").exists()]
    if missing:
        raise ConfigError([f"missing config file {config_dir / m}" for m in missing])
    cfg = {name: _read_yaml(config_dir / f"{name}.yaml") for name in CONFIG_FILES}
    cfg = apply_overrides(cfg, overrides)
    for kind in ("humans", "rooms"):
        cfg["run"].setdefault(kind, {})["root"] = _expand(cfg["run"][kind].get("root"))
    cfg["run"]["output_root"] = _expand(cfg["run"].get("output_root"))
    cfg["isaac"]["root"] = _expand(cfg["isaac"].get("root"))
    cfg["_config_dir"] = str(config_dir.resolve())
    errors = validate(cfg)
    if errors:
        raise ConfigError(errors)
    return cfg
