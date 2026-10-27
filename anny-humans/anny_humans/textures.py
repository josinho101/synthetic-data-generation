"""Texture operations with numpy + Pillow (ports of the MPFB pipeline's Blender image code).

Images are float32 arrays [H, W, 4] in sRGB 0..1 (alpha in channel 3)."""

import logging
from pathlib import Path

import numpy as np

_LOG = logging.getLogger("anny_humans.textures")


def hex_to_srgb(value: str) -> tuple:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def load_rgba(path, size=None) -> np.ndarray:
    from PIL import Image
    image = Image.open(path).convert("RGBA")
    if size is not None and image.size != tuple(size):
        image = image.resize(tuple(size), Image.LANCZOS)
    return np.asarray(image, dtype=np.float32) / 255.0


def fit_size(path, max_px: int) -> tuple:
    from PIL import Image
    with Image.open(path) as image:
        w, h = image.size
    scale = min(1.0, float(max_px) / max(w, h))
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


def save_png(pixels, path, alpha=True) -> Path:
    from PIL import Image
    data = (np.clip(pixels, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    if data.ndim == 2:
        Image.fromarray(data, "L").save(path)
    else:
        Image.fromarray(data if alpha else data[..., :3], "RGBA" if alpha else "RGB").save(path)
    return Path(path)


def srgb_to_lab(rgb):
    """sRGB 0..1 (..., 3) -> CIELAB (D65)."""
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((np.clip(rgb, 0, 1) + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], dtype=np.float32)
    xyz = (c @ m.T) / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_srgb(lab):
    """CIELAB (D65) (..., 3) -> sRGB 0..1 (clipped)."""
    fy = (lab[..., 0] + 16.0) / 116.0
    f = np.stack([fy + lab[..., 1] / 500.0, fy, fy - lab[..., 2] / 200.0], axis=-1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16.0 / 116.0) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m = np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]])
    lin = np.clip(xyz @ m.T, 0, 1)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055).astype(np.float32)


def match_tone(pixels, target_lab, strength=1.0, mask=None) -> tuple:
    """Match the median colour of the texture to target_lab (CIELAB): L* scaled (relative detail such as pores and
    creases kept), a*/b* shifted. -> (pixels, stats)."""
    lab = srgb_to_lab(pixels[..., :3])
    if mask is None:
        mask = (pixels[..., :3].max(axis=2) > 0.03) & (pixels[..., 3] > 0.5)   # UV islands, not the background
    before = np.median(lab[mask], axis=0)
    target = np.array(target_lab, dtype=np.float32)
    gain = 1.0 + float(strength) * (target[0] / max(float(before[0]), 1.0) - 1.0)
    lab[..., 0] *= gain
    lab[..., 1:] += float(strength) * (target[1:] - before[1:])
    out = pixels.copy()
    out[..., :3] = np.where(mask[..., None], lab_to_srgb(lab), pixels[..., :3])
    after = [round(float(v), 1) for v in np.median(lab[mask], axis=0)]
    stats = {"lab_before": [round(float(v), 1) for v in before], "lab_after": after}
    _LOG.info(f"skin tone matched: median L*a*b* {stats['lab_before']} -> {after} "
              f"(target {[round(float(v), 1) for v in target]})")
    return out, stats


def tint(pixels, rgb) -> np.ndarray:
    """Hair / eyebrows: grey level lifted and multiplied by the hair colour (strand detail kept)."""
    out = pixels.copy()
    grey = out[..., :3].mean(axis=2, keepdims=True)
    lift = 0.35 + 0.65 * grey / max(float(grey.max()), 1e-6)
    out[..., :3] = np.clip(lift * np.array(rgb, dtype=np.float32), 0, 1)
    return out


def recolor_garment(pixels, rgb) -> np.ndarray:
    """New garment colour, shading and detail kept: out = rgb x (luminance / bright luminance)."""
    out = pixels.copy()
    lum = out[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mask = (lum > 0.01) & (out[..., 3] > 0.5)
    if not mask.any():
        return out
    ref = max(float(np.percentile(lum[mask], 85)), 1e-3)
    shade = (lum / ref).clip(0.0, 1.15)[..., None]
    out[..., :3] = np.where(mask[..., None], (shade * np.array(rgb, dtype=np.float32)).clip(0, 1), out[..., :3])
    return out


def recolor_neutral(pixels, rgb, max_saturation=0.15, min_value=0.55) -> tuple:
    """Light, unsaturated pixels (e.g. a shoe's built-in sock) -> rgb, shading kept. -> (pixels, changed count)."""
    out = pixels.copy()
    rgb_in = out[..., :3]
    value = rgb_in.max(axis=2)
    saturation = (value - rgb_in.min(axis=2)) / np.maximum(value, 1e-6)
    mask = (value > min_value) & (saturation < max_saturation) & (out[..., 3] > 0.5)
    shade = (value / max(float(np.percentile(value[mask], 90)) if mask.any() else 1.0, 1e-6)).clip(0.5, 1.1)
    out[..., :3] = np.where(mask[..., None], (shade[..., None] * np.array(rgb, dtype=np.float32)).clip(0, 1), rgb_in)
    return out, int(mask.sum())


def fabric(weave_path, rgb, size=None) -> np.ndarray:
    """Solid fabric colour x cotton weave (generated garments such as the office skirt)."""
    weave = load_rgba(weave_path, size)[..., 0]
    out = np.ones(weave.shape + (4,), dtype=np.float32)
    out[..., :3] = np.array(rgb, dtype=np.float32) * weave[..., None]
    return out
