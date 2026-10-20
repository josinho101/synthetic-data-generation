"""Manifest: the resolved spec + layout of every room of a run (sampled once, reused by --resume / --only)."""

import json
import logging
from pathlib import Path

from ..layout.cameras import solve_cameras, solve_exam_cameras
from ..layout.solver import LayoutError, solve_layout
from .distributions import room_rng
from .sampler import sample_spec

_LOG = logging.getLogger("sdg_room.sampling")


def room_id(cfg: dict, index: int) -> str:
    var = cfg["variations"]
    return f"{var.get('id_prefix', 'R')}{index + 1:0{int(var.get('id_digits', 4))}d}"


# fixed layout: (config fingerprint, layout seed) -> (first accepted attempt, rejection reasons before it). All rooms
# share the layout, so they all start at that attempt instead of repeating the same rejected ones.
_FIXED_LAYOUT_ATTEMPT = {}


def _fingerprint(cfg: dict, lseed: int) -> str:
    import hashlib
    data = json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")}, sort_keys=True, default=str)
    return hashlib.sha1(f"{lseed}:{data}".encode()).hexdigest()


def build_room_spec(cfg: dict, index: int) -> dict:
    """Sample one room; resample (attempt + 1) until its layout can be solved."""
    var = cfg["variations"]
    rid = room_id(cfg, index)
    errors = []
    attempts = int(var.get("max_layout_attempts", 50))
    # randomize_layout false: every room uses the layout streams of one fixed layout (layout_seed, index 0), so all
    # rooms share the same layout and only the appearance (spec stream, per room) changes
    fixed = not var.get("randomize_layout", True)
    lseed = var.get("layout_seed") if var.get("layout_seed") is not None else var["seed"]
    lseed, lidx = (lseed, 0) if fixed else (var["seed"], index)
    key = _fingerprint(cfg, lseed) if fixed else None
    first = 0
    if key in _FIXED_LAYOUT_ATTEMPT:
        first, known = _FIXED_LAYOUT_ATTEMPT[key]
        errors = list(known)
    for attempt in range(first, attempts):
        rng = room_rng(var["seed"], index, attempt, "spec")
        room_seed = rng.randrange(1 << 31)
        spec = sample_spec(cfg, index, rid, rng, attempt, room_seed, room_rng(lseed, lidx, attempt, "layout_spec"))
        try:
            spec["layout"] = solve_layout(cfg, spec, room_rng(lseed, lidx, attempt, "layout"))
        except LayoutError as exc:
            errors.append(str(exc))
            _LOG.debug(f"{rid}: attempt {attempt} rejected: {exc}")
            continue
        spec["cameras"], spec["camera_coverage"] = solve_cameras(cfg, spec, room_rng(lseed, lidx, attempt, "cameras"))
        short = _coverage_shortfall(cfg, spec["camera_coverage"])
        cov_cfg = cfg["cameras"].get("coverage") or {}
        if short and cov_cfg.get("enforce", True) and attempt < attempts - 1:
            errors.append(f"camera coverage too low: {'; '.join(short)}")
            _LOG.debug(f"{rid}: attempt {attempt} rejected: camera coverage {short}")
            continue
        spec["layout"]["warnings"] += [f"room cameras see only {s_}" for s_ in short]
        spec["cameras"] += solve_exam_cameras(cfg, spec, room_rng(lseed, lidx, attempt, "exam_cameras"))
        spec["layout_rejections"] = errors
        if key:
            _FIXED_LAYOUT_ATTEMPT[key] = (attempt, list(errors))
        return spec
    raise LayoutError(f"{rid}: no valid layout after {len(errors)} attempts; last reasons: {errors[-3:]}")


def _coverage_shortfall(cfg: dict, coverage: dict) -> list:
    need = ((cfg.get("cameras") or {}).get("coverage") or {}).get("required", {})
    return [f"{100 * coverage[g]:.0f}% of '{g}' (required {100 * m:.0f}%)"
            for g, m in need.items() if g in coverage and coverage[g] < m - 1e-9]


def build_specs(cfg: dict) -> list:
    return [build_room_spec(cfg, i) for i in range(int(cfg["variations"]["count"]))]


def write_manifest(path, specs, meta: dict) -> None:
    Path(path).write_text(json.dumps({"meta": meta, "rooms": specs}, indent=2, default=str), encoding="utf-8")


def read_manifest(path) -> list:
    return json.loads(Path(path).read_text(encoding="utf-8"))["rooms"]
