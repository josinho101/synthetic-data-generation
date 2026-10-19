"""Somatotype -> MPFB body macros (weight, muscle, proportions)."""

import random


def sample_body_macros(rng: random.Random, somatotype_cfg: dict, name: str) -> dict:
    spec = somatotype_cfg[name]
    return {macro: round(rng.uniform(*spec[macro]), 4) for macro in ("weight", "muscle", "proportions")}


def sample_sex_macros(rng: random.Random, pop_cfg: dict, sex: str) -> dict:
    gender = rng.uniform(*pop_cfg["gender_macro"][sex])
    macros = {"gender": round(gender, 4), "cupsize": 0.5, "firmness": 0.5}
    if sex == "female":
        female = pop_cfg.get("female_macros") or {}
        for key in ("cupsize", "firmness"):
            if key in female:
                macros[key] = round(rng.uniform(*female[key]), 4)
    return macros
