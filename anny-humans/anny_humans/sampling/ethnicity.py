"""Ethnicity -> Anny race mix, skin tone (Monk scale) and base skin."""

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


def lab_to_rgb(lab) -> list:
    """CIELAB (D65) -> sRGB 0..1 (clipped)."""
    lightness, a, b = lab
    fy = (lightness + 16.0) / 116.0
    fx, fz = fy + a / 500.0, fy - b / 200.0

    def inv(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16.0 / 116.0) / 7.787

    x, y, z = 0.95047 * inv(fx), inv(fy), 1.08883 * inv(fz)
    lin = (3.2406 * x - 1.5372 * y - 0.4986 * z, -0.9689 * x + 1.8758 * y + 0.0415 * z,
           0.0557 * x - 0.2040 * y + 1.0570 * z)
    return [min(1.0, max(0.0, 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055)) for c in lin]


def sample_skin(rng: random.Random, appearance: dict, ethnicity: str, sex: str, age_years: int) -> dict:
    """Monk level -> reference colour (rgb_hex, for reporting) and skin ALBEDO target (albedo_lab,
    what the texture is matched to). Monk swatches are perceived colours (MST 1 L*=94, MST 10 L*=15);
    measured skin albedo spans roughly L* 27..72, so rendering uses albedo_lab."""
    profile = appearance["ethnicity_profiles"][ethnicity]
    skin_cfg = appearance["skin"]
    tone = int(weighted_choice(rng, profile["skin_tone_weights"]))
    base = hex_to_rgb(appearance["skin_tones_rgb"][tone])
    jitter = float(skin_cfg.get("tone_jitter", 0.0))
    factor = 1.0 + rng.uniform(-jitter, jitter)
    rgb = [min(1.0, c * factor) for c in base]
    lab = [float(v) for v in appearance["skin_albedo_lab"][tone]]
    lab = [round(lab[0] * factor, 2), round(lab[1] + rng.uniform(-1.0, 1.0), 2), round(lab[2] + rng.uniform(-1.5, 1.5), 2)]
    age_variant = "young"
    for name, (lo, hi) in skin_cfg["age_variant"].items():
        if lo <= age_years <= hi:
            age_variant = name
    texture_base = profile["base_skin"]
    dark_from = skin_cfg.get("dark_texture_from_mst")
    if dark_from is not None:  # photo texture closest in tone keeps detail (pores, creases) natural
        texture_base = "african" if tone >= int(dark_from) else ("caucasian" if texture_base == "african" else texture_base)
    return {
        "tone_mst": tone,
        "rgb_hex": rgb_to_hex(rgb),
        "albedo_lab": lab,
        "albedo_hex": rgb_to_hex(lab_to_rgb(lab)),
        "base_skin": f"{age_variant} {texture_base} {sex}",
    }
