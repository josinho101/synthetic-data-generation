"""Console progress: per-human lines with percentage, timing and ETA, plus a final summary."""

import logging
import time

_LOG = logging.getLogger("anny_humans.progress")


def fmt_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def describe(spec: dict, result: dict = None) -> str:
    """Short one-line description of a human (spec + achieved measurements)."""
    result = result or {}
    sex = "M" if spec.get("sex") == "male" else "F"
    parts = [f"{spec['id']} {sex} {spec.get('age_years', '?')}y {spec.get('ethnicity', '?'):<15} "
             f"{spec.get('somatotype', '?'):<20}"]
    if result.get("height_cm"):
        parts.append(f"{result['height_cm']:.1f}cm {result.get('weight_kg', 0):.1f}kg BMI {result.get('bmi', 0):.1f}")
    else:
        parts.append(f"target {spec.get('target_height_cm', 0):.1f}cm")
    parts.append(f"{spec.get('clothing_variant', '')}")
    return " ".join(parts)


class Progress:
    def __init__(self, total: int, stage: str = "build"):
        self.total = max(total, 1)
        self.stage = stage
        self.done = 0
        self.ok = self.warn = self.failed = 0
        self.started = time.monotonic()

    def start_item(self, spec: dict) -> None:
        _LOG.info(f"[{self.stage}]  start  {describe(spec)}")

    def finish_item(self, spec: dict, result: dict) -> None:
        self.done += 1
        status = result.get("status", "failed")
        if status == "ok":
            self.ok += 1
            mark = "OK  "
        elif status == "warn":
            self.warn += 1
            mark = "WARN"
        else:
            self.failed += 1
            mark = "FAIL"
        elapsed = time.monotonic() - self.started
        eta = elapsed / self.done * (self.total - self.done)
        pct = 100.0 * self.done / self.total
        line = (f"[{self.stage}]  [{self.done:>4}/{self.total} | {pct:5.1f}%] {mark} {describe(spec, result)} "
                f"| {result.get('duration_s', 0):.1f}s | elapsed {fmt_duration(elapsed)} ETA {fmt_duration(eta)}")
        if status == "failed":
            line += f" | {result.get('error', 'see log')} (log: {result.get('log', '')})"
        elif status == "warn" and result.get("warnings"):
            line += f" | warnings: {len(result['warnings'])}"
        (_LOG.error if status == "failed" else _LOG.info)(line)

    def elapsed(self) -> float:
        return time.monotonic() - self.started


def print_distribution_table(title: str, configured: dict, achieved: dict, total: int) -> None:
    """Configured percent vs achieved count/percent for one attribute."""
    _LOG.info(f"  {title}")
    for key in configured:
        count = achieved.get(key, 0)
        pct = 100.0 * count / total if total else 0.0
        _LOG.info(f"    {key:<22} configured {configured[key]:>6.1f}%   achieved {count:>4} ({pct:5.1f}%)")
