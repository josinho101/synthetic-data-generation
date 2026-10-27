"""Height and age sampling, and the age (years) -> Anny age phenotype mapping."""

import random


def truncated_normal(rng: random.Random, mean: float, sd: float, lo: float, hi: float) -> float:
    """Rejection sampling; falls back to clamping after 1000 tries."""
    for _ in range(1000):
        value = rng.gauss(mean, sd)
        if lo <= value <= hi:
            return value
    return min(max(mean, lo), hi)


def sample_height_cm(rng: random.Random, height_cfg: dict, sex: str, ethnicity: str) -> float:
    spec = height_cfg[sex]
    offset = float((height_cfg.get("ethnicity_offset_cm") or {}).get(ethnicity, 0.0))
    value = truncated_normal(rng, spec["mean"] + offset, spec["sd"], spec["min"], spec["max"])
    return round(value, 1)


def parse_band(band: str) -> tuple:
    lo, hi = str(band).split("-")
    return int(lo), int(hi)


def clip_band(band: str, age_range: tuple) -> tuple:
    """Band limits intersected with the configured age range (whole years)."""
    lo, hi = parse_band(band)
    lo, hi = max(lo, int(age_range[0])), min(hi, int(age_range[1]))
    if lo > hi:
        raise ValueError(f"age band {band} lies outside age_range {age_range[0]}-{age_range[1]}")
    return lo, hi


def sample_age_years(rng: random.Random, band: str, age_range: tuple = (0, 200)) -> int:
    lo, hi = clip_band(band, age_range)
    return rng.randint(lo, hi)


def age_to_anny(age_years: float, mapping: list) -> float:
    """Piecewise-linear interpolation over [[years, macro], ...]; clamped at both ends."""
    points = sorted(mapping)
    if age_years <= points[0][0]:
        return float(points[0][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if age_years <= x1:
            return float(y0 + (y1 - y0) * (age_years - x0) / (x1 - x0))
    return float(points[-1][1])
