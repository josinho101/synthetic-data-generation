"""Eyes, hair, eyebrows, eyelashes and gown colour picks."""

import random

from .ethnicity import weighted_choice


def _grey_probability(age_years: int, grey_from_age: int) -> float:
    if age_years <= grey_from_age:
        return 0.0
    return min(1.0, (age_years - grey_from_age) / max(1, 85 - grey_from_age))


def sample_looks(rng: random.Random, appearance: dict, clothing: dict, sex: str, age_years: int) -> dict:
    hair_cfg = appearance.get("hair") or {}
    style = weighted_choice(rng, hair_cfg[sex]["styles"]) if sex in hair_cfg else "none"
    colors = dict(hair_cfg.get("colors") or {"black": 1})
    if rng.random() < _grey_probability(age_years, int(hair_cfg.get("grey_from_age", 200))):
        hair_color = "grey"
    else:
        hair_color = weighted_choice(rng, {k: v for k, v in colors.items() if k != "grey"} or colors)
    eyebrows = (appearance.get("eyebrows") or {}).get("pool") or []
    eyelashes = (appearance.get("eyelashes") or {}).get("pool") or []
    gown_colors = clothing.get("gown_colors") or {}
    gown_color = weighted_choice(rng, {k: v["pct"] for k, v in gown_colors.items()}) if gown_colors else None
    return {
        "eyes": {"color": weighted_choice(rng, appearance["eyes"]["colors"])},
        "hair": {"style": style, "color": hair_color},
        "eyebrows": rng.choice(eyebrows) if eyebrows else None,
        "eyelashes": rng.choice(eyelashes) if eyelashes else None,
        "gown_color": gown_color,
    }
