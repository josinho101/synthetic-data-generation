"""Pattern masks for the gown fabric (white = 0, stripe colour = 1); top rows = white trim band."""

import math

import bpy


def _save(values, path, size) -> None:
    import numpy as np
    rgba = np.dstack([values, values, values, np.ones_like(values)]).astype(np.float32)
    image = bpy.data.images.new(path.stem, width=size, height=size, alpha=False)
    image.pixels[:] = rgba.ravel()
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()


def make_textures(out_dir, size: int = 512, stripes_per_tile: int = 4, stripe_width: float = 0.38) -> None:
    """stripes_mask.png (vertical stripes, v >= 0.9 white) and cotton_weave.png (subtle weave)."""
    import numpy as np
    y, x = np.mgrid[0:size, 0:size] / size          # row 0 = v 0 (bottom)
    stripes = ((x * stripes_per_tile) % 1.0 < stripe_width).astype(np.float32)
    pin = (np.abs(((x * stripes_per_tile) % 1.0) - 0.69) < 0.015).astype(np.float32) * 0.6
    mask = np.clip(stripes + pin, 0.0, 1.0)
    mask[y >= 0.9] = 0.0
    _save(mask, out_dir / "stripes_mask.png", size)
    rng = np.random.default_rng(7)
    weave = 0.5 + 0.25 * np.sin(2 * math.pi * 96 * x) * np.sin(2 * math.pi * 96 * y)
    _save(np.clip(0.92 + 0.06 * weave + rng.normal(0.0, 0.02, (size, size)), 0, 1), out_dir / "cotton_weave.png", size)
