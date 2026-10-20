"""Console progress: per-room lines with percentage, timing and ETA."""

import logging
import time

_LOG = logging.getLogger("sdg_room.progress")


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def describe(spec: dict) -> str:
    """Short one-line description of a room spec."""
    props = spec.get("layout", {}).get("props", [])
    return (f"{spec['id']} {spec['footprint_m'][0]:.2f}x{spec['footprint_m'][1]:.2f}m "
            f"wall={spec['wall_finish']:<6} floor={spec['floor_material']:<8} "
            f"det={spec['detector_side']:<5} {spec['cct_class']} {spec['cct_k']:.0f}K "
            f"{spec['lux_target']:.0f}lux support={spec['patient_support']:<9} props={len(props)}")


class Progress:
    def __init__(self, total: int, stage: str = "build"):
        self.total = max(total, 1)
        self.stage = stage
        self.done = self.ok = self.warn = self.failed = 0
        self.started = time.monotonic()

    def finish_item(self, spec: dict, result: dict) -> None:
        self.done += 1
        status = result.get("status", "failed")
        mark = {"ok": "OK  ", "warn": "WARN"}.get(status, "FAIL")
        if status == "ok":
            self.ok += 1
        elif status == "warn":
            self.warn += 1
        else:
            self.failed += 1
        elapsed = time.monotonic() - self.started
        eta = elapsed / self.done * (self.total - self.done)
        line = (f"[{self.stage}]  [{self.done:>4}/{self.total} | {100.0 * self.done / self.total:5.1f}%] {mark} "
                f"{describe(spec)} | {result.get('duration_s', 0):.1f}s | elapsed {fmt_duration(elapsed)} "
                f"ETA {fmt_duration(eta)}")
        if status == "failed":
            line += f" | {result.get('error', 'see log')} (log: {result.get('log', '')})"
        elif status == "warn" and result.get("warnings"):
            line += f" | warnings: {len(result['warnings'])}"
        (_LOG.error if status == "failed" else _LOG.info)(line)

    def elapsed(self) -> float:
        return time.monotonic() - self.started


def print_distribution_table(title: str, configured: dict, achieved: dict, total: int) -> None:
    """Configured share (from weights) vs achieved count/percent for one attribute."""
    weight_sum = sum(configured.values()) or 1.0
    _LOG.info(f"  {title}")
    for key, weight in configured.items():
        count = achieved.get(key, 0)
        pct = 100.0 * count / total if total else 0.0
        _LOG.info(f"    {key:<14} configured {100.0 * weight / weight_sum:>6.1f}%   achieved {count:>4} ({pct:5.1f}%)")
