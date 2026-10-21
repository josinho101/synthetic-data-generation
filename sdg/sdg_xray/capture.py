"""Capture planning (host side): which cameras each SD records, and the balanced choice for camera groups."""

import json
from pathlib import Path

from .config import ConfigError


def existing_group_counts(output_root, groups: dict) -> dict:
    """{group: {option: count}} over every SD in output_root (all run-*/SD.* folders, and SD.* folders of the older
    layout without run folders), from sd_info.json -> capture.groups."""
    counts = {g: {o: 0 for o in opts} for g, opts in groups.items()}
    root = Path(output_root)
    infos = sorted(root.glob("run-*/*/sd_info.json")) + sorted(root.glob("*/sd_info.json")) if root.exists() else []
    for info_path in infos:
        try:
            chosen = (json.loads(info_path.read_text()).get("capture") or {}).get("groups") or {}
        except (OSError, ValueError):
            continue
        for g, option in chosen.items():
            if g in counts and option in counts[g]:
                counts[g][option] += 1
    return counts


def choose_group_options(output_root, groups: dict, n_new: int) -> list:
    """One {group: option} per new SD, keeping each group's options at their target shares across the dataset:
    each SD takes the option that is furthest below its share (ties: config order)."""
    counts = existing_group_counts(output_root, groups)
    picks = []
    for _ in range(n_new):
        pick = {}
        for g, shares in groups.items():
            total = sum(counts[g].values()) + 1
            weight = sum(float(v) for v in shares.values()) or 1.0
            option = max(shares, key=lambda o: (float(shares[o]) / weight) * total - counts[g][o])
            counts[g][option] += 1
            pick[g] = option
        picks.append(pick)
    return picks


def every_n_frames(cfg: dict) -> int:
    """Simulated frames per captured image: isaac.fps / capture.fps (validated to be a whole number)."""
    return max(1, round(float(cfg["isaac"].get("fps", 30)) / float(cfg["capture"].get("fps", 30))))


def validate_capture(cfg: dict, sim_fps: float = 30.0) -> list:
    errors = []
    cams = cfg.get("cameras") or {}
    groups = cfg.get("groups") or {}
    for name, cam in cams.items():
        if bool(cam.get("camera")) == bool(cam.get("rig")):
            errors.append(f"capture.cameras.{name}: give either camera or rig")
        if cam.get("group") and cam["group"] not in groups:
            errors.append(f"capture.cameras.{name}.group {cam['group']!r} is not in capture.groups")
        if cam.get("enabled", True) is False and cam.get("group") and \
                float((groups.get(cam["group"]) or {}).get(name, 0)) > 0:
            errors.append(f"capture.cameras.{name} is disabled but has a share in capture.groups.{cam['group']}; "
                          f"set its share to 0")
    if not any(c.get("enabled", True) is not False for c in cams.values()):
        errors.append("capture.cameras: every camera is disabled (use --no-capture or capture.enabled: false instead)")
    for g, shares in groups.items():
        members = {n for n, c in cams.items() if c.get("group") == g}
        unknown = set(shares) - members
        if unknown:
            errors.append(f"capture.groups.{g}: {sorted(unknown)} are not cameras of group {g}")
        if any(float(v) < 0 for v in shares.values()) or sum(float(v) for v in shares.values()) <= 0:
            errors.append(f"capture.groups.{g}: shares must be >= 0 with a positive sum")
    if "every_n_frames" in cfg:
        errors.append("capture.every_n_frames was replaced by capture.fps (images per second, e.g. 2)")
    fps = cfg.get("fps", 30)
    if not isinstance(fps, (int, float)) or fps <= 0 or fps > sim_fps or \
            abs(sim_fps / fps - round(sim_fps / fps)) > 1e-6:
        options = [f"{sim_fps / n:g}" for n in range(1, int(sim_fps) + 1) if (sim_fps / n).is_integer()]
        errors.append(f"capture.fps must divide isaac.fps ({sim_fps:g}): one of {', '.join(options)}")
    if cfg.get("depth_format", "npy") not in ("npy", "png16"):
        errors.append("capture.depth_format must be npy or png16")
    rng = cfg.get("depth_preview_range_m", [0.3, 8.0])
    if not (isinstance(rng, list) and len(rng) == 2 and all(isinstance(v, (int, float)) for v in rng)
            and 0 <= rng[0] < rng[1]):
        errors.append("capture.depth_preview_range_m must be [near, far] in metres with 0 <= near < far")
    return errors


def cameras_for_sd(cfg: dict, group_pick: dict) -> list:
    """[{name, camera | rig}] recorded by one SD: all enabled ungrouped cameras + the picked camera of each group."""
    out = []
    for name, cam in (cfg.get("cameras") or {}).items():
        if cam.get("enabled", True) is False:
            continue
        group = cam.get("group")
        if group and group_pick.get(group) != name:
            continue
        out.append({k: v for k, v in dict(cam, name=name).items() if k != "enabled"})
    if not out:
        raise ConfigError("capture is enabled but no camera is selected")
    return out


# measured average sizes per image (MB): RGB png of the room cameras ~0.45, depth png16 ~0.15, depth npy (float32)
# 3.7 at 1280x720; jpg ~0.15; 8-bit depth preview png ~0.1 (estimate)
_MB = {"png": 0.45, "jpg": 0.15, "png16": 0.15, "npy": 3.7, "preview": 0.1}


def capture_disk_estimate(cfg: dict, visits: list) -> float:
    """Approximate bytes the capture of these visits will write (for the free-disk check)."""
    cap = cfg["capture"]
    fps = float(cfg["isaac"].get("fps", 30)) / every_n_frames(cfg)
    per_frame = 0.0
    streams = cap.get("streams") or {}
    for v in visits:
        n_cams = len((v.get("capture") or {}).get("cameras") or [])
        seconds = 20.0 + 11.0 * len(v.get("projections") or [])         # chest (3 projections): ~52 s simulated
        mb = (_MB[cap.get("rgb_format", "png")] if streams.get("rgb", True) else 0.0) + \
             ((_MB[cap.get("depth_format", "png16")] + (_MB["preview"] if cap.get("depth_preview", True) else 0.0))
              if streams.get("depth", True) else 0.0)
        per_frame += n_cams * mb * fps * seconds
    return per_frame * 1e6
