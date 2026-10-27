"""Face detail targets, mirroring MPFB's randomizationservice.pick_random_details semantics.

Anny ships MPFB's target catalogue (anny/data/mpfb2/targets/target.json); model.py maps the picked target names
to Anny local changes (the "incr" target of a category is +value, its "decr" opposite -value).

Per configured section: draw a pick count in [min, max], pick that many distinct
categories from the name-sorted pool, then per category draw a sign (decr/incr)
and a magnitude in [0.25 * deviation, deviation]. Sided categories (left/right)
get the same value on both sides when `symmetric` is on.
"""

import json
import random
from pathlib import Path


def load_target_catalogue(data_dir=None) -> dict:
    """Section name -> list of category dicts, from <data_dir>/targets/target.json (default: Anny's mpfb2 data)."""
    if data_dir is None:
        from anny.paths import get_anny_root_dir
        data_dir = get_anny_root_dir() / "data" / "mpfb2"
    path = Path(data_dir) / "targets" / "target.json"
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {section: (body or {}).get("categories", []) for section, body in data.items()}


def _targets_for(category: dict, sign: str, side: str) -> str:
    opposites = category.get("opposites") or {}
    return opposites.get(f"{sign}-{side}", "")


def _category_stack(rng, category: dict, deviation: float, symmetric: bool) -> list:
    opposites = category.get("opposites") or {}
    one_sided = not any(opposites.values())
    stack = []
    sides = ["left", "right"] if category.get("has_left_and_right") else ["unsided"]
    shared = None
    for side in sides:
        if shared is None or not symmetric:
            sign = "positive" if (one_sided or rng.random() < 0.5) else "negative"
            value = rng.uniform(0.25 * deviation, deviation)
            shared = (sign, value)
        sign, value = shared
        name = _targets_for(category, sign, side) if not one_sided else (category.get("targets") or [""])[0]
        if name:
            stack.append({"target": name, "value": round(value, 4)})
    return stack


def sample_face_targets(rng: random.Random, face_cfg: dict, catalogue: dict) -> list:
    """Return a flat [{"target": name, "value": float}, ...] list (MPFB target names, value > 0)."""
    symmetric = bool(face_cfg.get("symmetric", True))
    stack = []
    for section in sorted((face_cfg.get("sections") or {}).keys()):
        lo, hi, deviation = face_cfg["sections"][section]
        pool = sorted(catalogue.get(section, []), key=lambda c: str(c.get("name", "")).lower())
        if not pool:
            continue
        picks = min(rng.randint(int(lo), int(hi)), len(pool))
        for category in rng.sample(pool, picks):
            stack.extend(_category_stack(rng, category, float(deviation), symmetric))
    return stack
