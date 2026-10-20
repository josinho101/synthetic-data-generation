"""Procedural, tileable textures (numpy + Pillow). Every generator returns the texture's physical size (m)
so meshes can be given UVs in texture repeats."""

import numpy as np
from PIL import Image, ImageDraw

from ..sampling.distributions import hex_to_rgb


def _periodic_noise(res: int, seed: int, cutoff: float) -> np.ndarray:
    """Tileable noise in [-1, 1]: white noise low-pass filtered in the frequency domain (FFT => periodic)."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal((res, res))
    f = np.fft.fftfreq(res)
    fx, fy = np.meshgrid(f, f, indexing="ij")
    filt = np.exp(-(fx ** 2 + fy ** 2) / (2 * cutoff ** 2))
    noise = np.real(np.fft.ifft2(np.fft.fft2(white) * filt))
    return noise / (np.abs(noise).max() + 1e-12)


def _save(arr: np.ndarray, path) -> None:
    Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8)).save(path)


def _base(res, color):
    return np.ones((res, res, 3)) * np.array(hex_to_rgb(color))[None, None, :]


def vinyl(path, color, speckle, seed, res=1024, size_m=1.0) -> float:
    img = _base(res, color)
    cloud = _periodic_noise(res, seed, 0.01) * 0.04
    rng = np.random.default_rng(seed + 1)
    dots = rng.random((res, res))
    flecks = np.where(dots > 0.985, rng.uniform(-1, 1, (res, res)) * speckle * 4, 0.0)
    fine = _periodic_noise(res, seed + 2, 0.25) * speckle
    img = img * (1 + cloud + fine)[..., None] + flecks[..., None]
    _save(img, path)
    return size_m


def tiles(path, color, grout_color, tile_m, seed, res=1024, n=4, grout_m=0.004, variation=0.04) -> float:
    """n x n tiles with grout lines and slight per-tile shade variation."""
    size_m = n * tile_m
    img = _base(res, color)
    rng = np.random.default_rng(seed)
    px = res / n
    shade = rng.uniform(-variation, variation, (n, n))
    idx = (np.arange(res) / px).astype(int).clip(0, n - 1)
    img *= (1 + shade[idx][:, idx])[..., None]
    img *= (1 + _periodic_noise(res, seed + 3, 0.2) * 0.02)[..., None]
    g = max(1, int(round(grout_m / size_m * res / 2)))
    grout = np.zeros(res, dtype=bool)
    for k in range(n):
        c = int(round(k * px))
        grout[np.arange(c - g, c + g) % res] = True
    mask = grout[:, None] | grout[None, :]
    img[mask] = np.array(hex_to_rgb(grout_color))
    _save(img, path)
    return size_m


def concrete(path, color, seed, res=1024, size_m=2.0) -> float:
    img = _base(res, color)
    shade = (_periodic_noise(res, seed, 0.004) * 0.10 + _periodic_noise(res, seed + 1, 0.03) * 0.05 +
             _periodic_noise(res, seed + 2, 0.3) * 0.03)
    rng = np.random.default_rng(seed + 4)
    pores = np.where(rng.random((res, res)) > 0.997, -0.25, 0.0)
    img = img * (1 + shade + pores)[..., None]
    _save(img, path)
    return size_m


def ceiling_grid(path, color, tbar_color, grid_m, seed, res=512, n=2) -> float:
    size_m = n * grid_m
    img = _base(res, color)
    rng = np.random.default_rng(seed)
    img *= (1 + np.where(rng.random((res, res)) > 0.6, -0.04, 0.0) + _periodic_noise(res, seed, 0.2) * 0.02)[..., None]
    g = max(2, int(round(0.012 / size_m * res)))
    bar = np.zeros(res, dtype=bool)
    for k in range(n):
        c = int(round(k * res / n))
        bar[np.arange(c - g, c + g) % res] = True
    img[bar[:, None] | bar[None, :]] = np.array(hex_to_rgb(tbar_color))
    _save(img, path)
    return size_m


def detector_front(path, color, housing_m, active_m, chambers=3, res=1024) -> None:
    """Front face of the detector: active-area outline, centre cross-hair and AEC chamber marks."""
    w, h = housing_m
    img = Image.new("RGB", (res, int(res * h / w)), tuple(int(c * 255) for c in hex_to_rgb(color)))
    d = ImageDraw.Draw(img)
    sx, sy = img.width / w, img.height / h
    aw, ah = active_m
    x0, y0 = (w - aw) / 2 * sx, (h - ah) / 2 * sy
    x1, y1 = x0 + aw * sx, y0 + ah * sy
    line = (70, 80, 90)
    d.rectangle([x0, y0, x1, y1], outline=line, width=max(2, res // 300))
    cx, cy = img.width / 2, img.height / 2
    d.line([cx - 0.04 * sx, cy, cx + 0.04 * sx, cy], fill=line, width=max(2, res // 400))
    d.line([cx, cy - 0.04 * sy, cx, cy + 0.04 * sy], fill=line, width=max(2, res // 400))
    cw = 0.06
    centres = [(cx, cy - 0.06 * sy), (cx - 0.11 * sx, cy - 0.12 * sy), (cx + 0.11 * sx, cy - 0.12 * sy)][:chambers]
    for px, py in centres:
        d.rectangle([px - cw / 2 * sx, py - cw / 2 * sy, px + cw / 2 * sx, py + cw / 2 * sy], outline=line,
                    width=max(2, res // 400))
    img.save(path)


def footprints(path, color, size_m=(0.50, 0.40), spacing=0.24, res=512) -> None:
    """RGBA decal: two foot outlines, toes pointing to the bottom edge of the image (local -Y)."""
    w, h = size_m
    img = Image.new("RGBA", (res, int(res * h / w)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = img.width / w
    rgba = tuple(int(c * 255) for c in hex_to_rgb(color)) + (255,)
    cy = img.height / 2
    for side in (-1, 1):
        cx = img.width / 2 + side * spacing / 2 * s
        fw, fl = 0.095 * s, 0.25 * s
        d.ellipse([cx - fw / 2, cy - fl / 2 + 0.04 * s, cx + fw / 2, cy + fl / 2], fill=rgba)        # sole
        d.ellipse([cx - fw * 0.42, cy - fl / 2 + 0.01 * s, cx + fw * 0.42, cy - fl / 2 + 0.09 * s], fill=rgba)   # heel
        for k, (dx, r) in enumerate(((-0.030, 0.016), (-0.010, 0.013), (0.008, 0.012), (0.024, 0.011), (0.037, 0.009))):
            tx = cx + side * dx * s
            ty = cy + fl / 2 + 0.018 * s
            d.ellipse([tx - r * s, ty - r * s, tx + r * s, ty + r * s], fill=rgba)
    img.save(path)
