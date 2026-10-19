"""Ethnicity -> MPFB race mix, skin tone (Monk scale) and base skin."""

import random

RACES = ("asian", "caucasian", "african")


def weighted_choice(rng: random.Random, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[float(weights[k]) for k in keys], k=1)[0]


def sample_race_mix(rng: random.Random, profile: dict) -> dict:
    jitter = float(profile.get("jitter", 0.0))
    raw = {r: max(0.0, float(profile["race_mix"][r]) + rng.uniform(-jitter, jitter)) for r in RACES}
    total = sum(raw.values()) or 1.0
    return {r: round(v / total, 4) for r, v in raw.items()}


def hex_to_rgb(value: str) -> list:
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in rgb)


def sample_skin(rng: random.Random, appearance: dict, ethnicity: str, sex: str, age_years: int) -> dict:
    profile = appearance["ethnicity_profiles"][ethnicity]
    tone = int(weighted_choice(rng, profile["skin_tone_weights"]))
    base = hex_to_rgb(appearance["skin_tones_rgb"][tone])
    jitter = float(appearance["skin"].get("tone_jitter", 0.0))
    factor = 1.0 + rng.uniform(-jitter, jitter)
    rgb = [min(1.0, c * factor) for c in base]
    age_variant = "young"
    for name, (lo, hi) in appearance["skin"]["age_variant"].items():
        if lo <= age_years <= hi:
            age_variant = name
    return {
        "tone_mst": tone,
        "rgb_hex": rgb_to_hex(rgb),
        "base_skin": f"{age_variant} {profile['base_skin']} {sex}",
    }
