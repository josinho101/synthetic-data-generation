"""Skin: MakeHuman photo skin (mhmat) matched to the human's tone, plus generated detail maps.

Albedo: the system skin closest to "<age variant> <ethnicity> <sex>" (MPFB's choice rule), resized and colour-matched
to the skin_albedo_lab target in CIELAB. Detail maps (seeded per human, UV space of the hm08 mesh):
  normal    : tangent-space (OpenGL, +Y = +v) from a height field of pores and age-scaled fine wrinkles
  roughness : lower on the head / face (oilier), higher on the body, with pore-scale variation
Subsurface radius (Isaac RTX OmniSurface) is interpolated between light and dark skin by the Monk level.
"""

import logging
from pathlib import Path

import numpy as np

from . import textures

_LOG = logging.getLogger("anny_humans.skin")

_EXCLUDE = ("special", "suit", "toon")


def find_system_skin(assets_dir, base_skin: str):
    """Best matching MakeHuman system skin .mhmat for e.g. 'young caucasian female' (None if none installed)."""
    if assets_dir is None:
        return None
    words = base_skin.lower().split()
    exact = "_".join(words)
    scored = []
    for path in sorted(Path(assets_dir, "skins").glob("*/*.mhmat")):
        name = path.stem.lower()
        if any(bad in name for bad in _EXCLUDE):          # skin-suits / toon shaders are not skin
            continue
        score = sum(w in name.split("_") for w in words) + (2 if name == exact else 0)
        scored.append((score, name, path))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2] if scored and scored[0][0] >= 2 else None


def _noise(rng, shape, sigma_px, anisotropy=(1.0, 1.0)):
    from scipy.ndimage import gaussian_filter
    field = gaussian_filter(rng.standard_normal(shape).astype(np.float32),
                            (sigma_px * anisotropy[0], sigma_px * anisotropy[1]), mode="wrap")
    return field / max(float(field.std()), 1e-6)


def _head_mask(size: int):
    """UV-space head region from Anny's body-part segmentation (hm08 UV layout), soft edged."""
    from PIL import Image
    from scipy.ndimage import gaussian_filter
    from anny.paths import get_anny_root_dir
    path = get_anny_root_dir() / "data" / "segmentation" / "body_parts_segmentation.png"
    if not path.exists():
        return np.zeros((size, size), dtype=np.float32)
    seg = np.asarray(Image.open(path).convert("RGB").resize((size, size), Image.NEAREST), dtype=np.int32)
    head = np.all(np.abs(seg - np.array([90, 86, 255])) < 8, axis=2).astype(np.float32)
    return gaussian_filter(head, size / 256.0)


def detail_maps(seed: int, size: int, age_years: float, detail: dict, roughness: float) -> tuple:
    """-> (normal RGB [S, S, 3] 0..1, roughness [S, S] 0..1)."""
    rng = np.random.default_rng(seed)
    scale = size / 2048.0
    pore_px = float(detail.get("pore_scale_px", 1.6)) * scale
    height = 0.7 * _noise(rng, (size, size), pore_px) + 0.3 * _noise(rng, (size, size), pore_px * 0.5)
    decades = max(0.0, (float(age_years) - 30.0) / 10.0)
    wrinkle = float(detail.get("wrinkle_gain_per_decade", 0.12)) * decades
    if wrinkle > 0:   # fine horizontal creases (stretched noise)
        height += wrinkle * _noise(rng, (size, size), 2.5 * scale, (0.5, 6.0))
    strength = float(detail.get("normal_strength", 0.35))
    gy, gx = np.gradient(height)
    n = np.stack([-gx * strength, gy * strength, np.ones_like(height)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    normal = n * 0.5 + 0.5
    lo, hi = detail.get("roughness_range", [0.32, 0.62])
    head = _head_mask(size)
    rough = roughness + 0.04 * _noise(rng, (size, size), 6.0 * scale) - 0.06 * height.clip(-2, 2) / 2.0
    rough -= 0.08 * head
    return normal.astype(np.float32), np.clip(rough, lo, hi).astype(np.float32)


def subsurface(appearance: dict, tone_mst: int) -> dict:
    sss = (appearance.get("skin") or {}).get("subsurface") or {}
    if not sss.get("enabled", False):
        return {}
    t = (int(tone_mst) - 1) / 9.0
    radius = (1 - t) * np.array(sss["radius_mm_light"], dtype=np.float64) + t * np.array(sss["radius_mm_dark"])
    return {"weight": float(sss.get("weight", 0.35)), "radius_mm": [round(float(r), 3) for r in radius]}


def build_skin(spec: dict, appearance: dict, assets_dir, textures_dir: Path, report: dict) -> dict:
    """Write <id>_skin.png (+ _skin_normal.png, _skin_roughness.png). -> material / metadata info."""
    skin_cfg = appearance["skin"]
    hid = spec["id"]
    size = int(skin_cfg.get("texture_resolution", 2048))
    source = skin_cfg.get("source", "auto")
    mhmat = find_system_skin(assets_dir, spec["skin"]["base_skin"]) if source in ("auto", "mhmat") else None
    linear = [float(c) for c in textures.srgb_to_linear(textures.hex_to_srgb(spec["skin"]["albedo_hex"]))]
    info = {"source": "flat", "texture": None, "normal": None, "roughness_map": None, "tone": {},
            "albedo_linear": linear, "roughness": float(skin_cfg.get("roughness", 0.45)),
            "subsurface": subsurface(appearance, spec["skin"]["tone_mst"])}
    diffuse = None
    if mhmat:
        from .proxy_fit import parse_mhmat
        diffuse = parse_mhmat(mhmat).get("diffuseTexture")
    if diffuse is None:
        message = ("appearance.skin.source=mhmat but no system skin found" if source == "mhmat"
                   else "no MakeHuman system skin installed") + "; using a flat skin colour"
        report["warnings" if source == "mhmat" else "notes"].append(message)
    else:
        pixels = textures.load_rgba(diffuse, (size, size))
        pixels, info["tone"] = textures.match_tone(pixels, spec["skin"]["albedo_lab"],
                                                   skin_cfg.get("tone_match_strength", 1.0))
        textures.save_png(pixels, textures_dir / f"{hid}_skin.png", alpha=False)
        info.update(source=f"mhmat:{mhmat}", texture=f"{hid}_skin.png")
    detail = skin_cfg.get("detail") or {}
    if float(detail.get("normal_strength", 0.0)) > 0:
        normal, rough = detail_maps(int(spec["seed"]) % (2 ** 32), size, spec["age_years"], detail, info["roughness"])
        textures.save_png(np.dstack([normal, np.ones(normal.shape[:2], np.float32)]), textures_dir / f"{hid}_skin_normal.png",
                          alpha=False)
        textures.save_png(rough, textures_dir / f"{hid}_skin_roughness.png")
        info.update(normal=f"{hid}_skin_normal.png", roughness_map=f"{hid}_skin_roughness.png")
    _LOG.info(f"skin {info['source']}, MST {spec['skin']['tone_mst']} albedo {spec['skin']['albedo_hex']}, "
              f"subsurface {info['subsurface']}")
    return info
