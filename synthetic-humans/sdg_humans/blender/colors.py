"""Colour conversions (stdlib)."""


def hex_to_srgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(value: str) -> tuple:
    return tuple(srgb_to_linear(c) for c in hex_to_srgb(value)) + (1.0,)


def scale_rgba(rgba: tuple, factors: tuple) -> tuple:
    return tuple(min(1.0, c * f) for c, f in zip(rgba[:3], factors)) + (1.0,)
