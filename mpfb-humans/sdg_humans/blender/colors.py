"""Colour conversions (stdlib)."""


def hex_to_srgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(value: str) -> tuple:
    return tuple(srgb_to_linear(c) for c in hex_to_srgb(value)) + (1.0,)


def srgb_to_lab_np(rgb):
    """sRGB 0..1 (..., 3) numpy array -> CIELAB (D65)."""
    import numpy as np
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((np.clip(rgb, 0, 1) + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], dtype=np.float32)
    xyz = (c @ m.T) / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb_np(lab):
    """CIELAB (D65) (..., 3) numpy array -> sRGB 0..1 (clipped)."""
    import numpy as np
    fy = (lab[..., 0] + 16.0) / 116.0
    f = np.stack([fy + lab[..., 1] / 500.0, fy, fy - lab[..., 2] / 200.0], axis=-1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16.0 / 116.0) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    lin = np.clip(xyz @ m.T, 0, 1)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055).astype(np.float32)


def scale_rgba(rgba: tuple, factors: tuple) -> tuple:
    return tuple(min(1.0, c * f) for c, f in zip(rgba[:3], factors)) + (1.0,)
