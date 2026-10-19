"""Skin: MakeHuman photo skin (mhmat) or MPFB layered skin, baked, then colour-matched to the tone.

The baked albedo's median colour is matched to the human's skin_albedo_lab target in CIELAB:
L* is scaled (relative detail such as pores and creases is kept), a*/b* are shifted.
"""

import logging
from pathlib import Path

import bpy

from . import bake, colors

_LOG = logging.getLogger("sdg_humans.blender.skin")

_SKIN_GROUPS = ("bodygroup", "facegroup", "earsgroup")
_EXCLUDE = ("special", "suit", "toon")


def find_system_skin(ns, base_skin: str):
    """Best matching MakeHuman system skin .mhmat for e.g. 'young caucasian female'."""
    try:
        candidates = ns.AssetService.list_mhmat_assets("skins")
    except Exception:  # noqa: BLE001
        return None
    words = base_skin.lower().split()
    exact = "_".join(words)
    scored = []
    for path in candidates:
        name = Path(str(path)).stem.lower()
        if any(bad in name for bad in _EXCLUDE):          # skin-suits / toon shaders are not skin
            continue
        score = sum(w in name.split("_") for w in words) + (2 if name == exact else 0)
        scored.append((score, name, str(path)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2] if scored and scored[0][0] >= 2 else None


def _tint_layered(material, rgba) -> None:
    for node in material.node_tree.nodes:
        if node.type != "GROUP":
            continue
        if node.name == "colorgroup":
            node.inputs["SkinColor"].default_value = rgba
            node.inputs["SkinOverride"].default_value = 1.0
            node.inputs["LipsColor"].default_value = colors.scale_rgba(rgba, (0.85, 0.55, 0.55))
            node.inputs["LipsOverride"].default_value = 0.6
        elif node.name in _SKIN_GROUPS and "SkinColor" in node.inputs:
            node.inputs["SkinColor"].default_value = rgba


def apply_skin(ns, basemesh, spec: dict, appearance: dict, asset_report: dict) -> dict:
    skin_cfg = appearance["skin"]
    source = skin_cfg.get("source", "auto")
    mhmat = find_system_skin(ns, spec["skin"]["base_skin"]) if source in ("auto", "mhmat") else None
    if source == "mhmat" and not mhmat:
        asset_report["warnings"].append("skin.source=mhmat but no system skin found; using layered skin")
    rgba = colors.hex_to_linear_rgba(spec["skin"].get("albedo_hex") or spec["skin"]["rgb_hex"])
    if mhmat:
        ns.HumanService.set_character_skin(mhmat, basemesh, skin_type="MAKESKIN", material_instances=False)
        used = f"mhmat:{mhmat}"
    else:
        ns.HumanService.set_character_skin(None, basemesh, skin_type="LAYERED")
        _tint_layered(basemesh.active_material, rgba)
        used = "layered"
    _LOG.info(f"skin source {used}, tone MST {spec['skin']['tone_mst']} albedo {spec['skin'].get('albedo_hex')}")
    return {"source": used}


def match_tone(path, target_lab, strength=1.0) -> dict:
    """Match the median skin colour of the baked texture to target_lab (in place). Returns stats."""
    import numpy as np
    image = bpy.data.images.load(str(path), check_existing=False)
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, 4)
    lab = colors.srgb_to_lab_np(pixels[..., :3])
    mask = (pixels[..., :3].max(axis=2) > 0.03) & (pixels[..., 3] > 0.5)   # UV islands, not the background
    before = np.median(lab[mask], axis=0)
    target = np.array(target_lab, dtype=np.float32)
    strength = float(strength)
    gain = 1.0 + strength * (target[0] / max(float(before[0]), 1.0) - 1.0)
    lab[..., 0] *= gain
    lab[..., 1:] += strength * (target[1:] - before[1:])
    pixels[..., :3] = np.where(mask[..., None], colors.lab_to_srgb_np(lab), pixels[..., :3])
    image.pixels[:] = pixels.ravel()
    image.filepath_raw = str(path)
    image.save()
    bpy.data.images.remove(image)
    after = [round(float(v), 1) for v in np.median(lab[mask], axis=0)]
    _LOG.info(f"skin tone matched: median L*a*b* {[round(float(v), 1) for v in before]} -> {after} "
              f"(target {[round(float(v), 1) for v in target]})")
    return {"lab_before": [round(float(v), 1) for v in before], "lab_after": after}


def bake_skin(basemesh, textures_dir, human_id: str, appearance: dict, target_lab=None) -> tuple:
    """Bake the skin albedo (and match it to target_lab). Returns (texture file name, tone stats)."""
    skin_cfg = appearance["skin"]
    path = bake.bake_diffuse_color(basemesh, textures_dir / f"{human_id}_skin.png",
                                   int(skin_cfg.get("bake_resolution", 2048)))
    stats = match_tone(path, target_lab, skin_cfg.get("tone_match_strength", 1.0)) if target_lab else {}
    material = bake.simple_material(f"{human_id}_skin", image_path=path,
                                    roughness=float(skin_cfg.get("roughness", 0.45)))
    bake.replace_materials(basemesh, material)
    return path.name, stats
