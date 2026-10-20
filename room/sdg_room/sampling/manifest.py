"""Manifest: the resolved spec + layout of every room of a run (sampled once, reused by --resume / --only)."""

import json
import logging
from pathlib import Path

from ..layout.cameras import solve_cameras
from ..layout.solver import LayoutError, solve_layout
from .distributions import room_rng
from .sampler import sample_spec

_LOG = logging.getLogger("sdg_room.sampling")


def room_id(cfg: dict, index: int) -> str:
    var = cfg["variations"]
    return f"{var.get('id_prefix', 'R')}{index + 1:0{int(var.get('id_digits', 4))}d}"


def build_room_spec(cfg: dict, index: int) -> dict:
    """Sample one room; resample (attempt + 1) until its layout can be solved."""
    var = cfg["variations"]
    rid = room_id(cfg, index)
    errors = []
    attempts = int(var.get("max_layout_attempts", 50))
    for attempt in range(attempts):
        rng = room_rng(var["seed"], index, attempt, "spec")
        room_seed = rng.randrange(1 << 31)
        spec = sample_spec(cfg, index, rid, rng, attempt, room_seed)
        try:
            spec["layout"] = solve_layout(cfg, spec, room_rng(var["seed"], index, attempt, "layout"))
        except LayoutError as exc:
            errors.append(str(exc))
            _LOG.debug(f"{rid}: attempt {attempt} rejected: {exc}")
            continue
        spec["cameras"], spec["camera_coverage"] = solve_cameras(cfg, spec, room_rng(var["seed"], index, attempt,
                                                                                    "cameras"))
        short = _coverage_shortfall(cfg, spec["camera_coverage"])
        cov_cfg = cfg["cameras"].get("coverage") or {}
        if short and cov_cfg.get("enforce", True) and attempt < attempts - 1:
            errors.append(f"camera coverage too low: {'; '.join(short)}")
            _LOG.debug(f"{rid}: attempt {attempt} rejected: camera coverage {short}")
            continue
        spec["layout"]["warnings"] += [f"room cameras see only {s_}" for s_ in short]
        spec["layout_rejections"] = errors
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
