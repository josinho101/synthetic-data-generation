"""Small seeded sampling helpers (stdlib `random.Random`, deterministic for a given seed string)."""

import colorsys
import random


def room_rng(seed: int, index: int, attempt: int = 0, stream: str = "spec") -> random.Random:
    """Independent, reproducible stream per room / attempt / purpose."""
    return random.Random(f"{seed}:{index}:{attempt}:{stream}")


def weighted_choice(rng: random.Random, weights: dict):
    keys = [k for k, w in weights.items() if w > 0]
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def uniform(rng: random.Random, rng_range) -> float:
    lo, hi = rng_range
    return lo if lo == hi else rng.uniform(lo, hi)


def int_range(rng: random.Random, rng_range) -> int:
    lo, hi = (int(v) for v in rng_range)
    return rng.randint(lo, hi)


def truncated_normal(rng: random.Random, mean, sd, lo, hi, tries=1000) -> float:
    for _ in range(tries):
        value = rng.gauss(mean, sd)
        if lo <= value <= hi:
            return value
    return min(max(mean, lo), hi)


def hex_to_rgb(value: str):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    return "#" + "".join(f"{int(round(min(max(c, 0.0), 1.0) * 255)):02x}" for c in rgb)


def _to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _from_linear(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def hex_to_lab(value: str):
    """sRGB hex -> CIELAB (D65)."""
    r, g, b = (_to_linear(c) for c in hex_to_rgb(value))
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def lab_to_hex(lab) -> str:
    L, a, b = lab
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200
    x, y, z = ((t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787) for t in (fx, fy, fz))
    x, z = x * 0.95047, z * 1.08883
    r = 3.2406 * x - 1.5372 * y - 0.4986 * z
    g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    bl = 0.0557 * x - 0.2040 * y + 1.0570 * z
    return rgb_to_hex([_from_linear(min(max(c, 0.0), 1.0)) for c in (r, g, bl)])


def delta_e(hex_a: str, hex_b: str) -> float:
    return sum((p - q) ** 2 for p, q in zip(hex_to_lab(hex_a), hex_to_lab(hex_b))) ** 0.5


def separate_color(color: str, reference: str, min_delta_e: float) -> str:
    """`color` moved in lightness away from `reference` until their Delta E >= min_delta_e (darker first)."""
    if min_delta_e <= 0 or delta_e(color, reference) >= min_delta_e:
        return color
    L, a, b = hex_to_lab(color)
    for direction in (-1, 1):
        for step in range(1, 101):
            cand = lab_to_hex((L + direction * step, a, b))
            if delta_e(cand, reference) >= min_delta_e:
                return cand
    return color


def jitter_color(rng: random.Random, hex_color: str, jitter: dict) -> str:
    """Random HSV offset (hue / sat / val amplitudes from config) around a base colour."""
    h, s, v = colorsys.rgb_to_hsv(*hex_to_rgb(hex_color))
    h = (h + rng.uniform(-1, 1) * jitter.get("hue", 0.0)) % 1.0
    s = min(max(s + rng.uniform(-1, 1) * jitter.get("sat", 0.0), 0.0), 1.0)
    v = min(max(v + rng.uniform(-1, 1) * jitter.get("val", 0.0), 0.0), 1.0)
    return rgb_to_hex(colorsys.hsv_to_rgb(h, s, v))
