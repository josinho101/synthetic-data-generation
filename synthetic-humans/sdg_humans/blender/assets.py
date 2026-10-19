"""Body parts (eyes, eyebrows, eyelashes, hair) and clothing via MPFB MHCLO assets."""

import logging
import random
from pathlib import Path

import bpy

from .. import clothing_match
from ..paths import ASSETS_DIR
from . import colors, eyes, garment_fit, gown_style, materials

_LOG = logging.getLogger("sdg_humans.blender.assets")


def _candidates(ns, subdir: str) -> list:
    try:
        paths = ns.AssetService.list_mhclo_assets(subdir)
    except Exception as exc:  # noqa: BLE001
        _LOG.debug(f"no {subdir} assets: {exc}")
        return []
    return [{"name": Path(p).stem, "path": str(p), "pack": None} for p in paths]


def _add_mhclo(ns, path: str, basemesh, asset_type: str):
    return ns.HumanService.add_mhclo_asset(path, basemesh, asset_type=asset_type, subdiv_levels=0,
                                           material_type="MAKESKIN")


def _hair_tint(appearance: dict, spec: dict):
    return (appearance.get("hair") or {}).get("rgb", {}).get(spec["hair"]["color"])


def delete_group_name(mhclo_path) -> str:
    """Name of the basemesh delete group MPFB creates for a clothes asset."""
    return "Delete." + Path(mhclo_path).stem.replace(" ", "_")


def _pick_color(clothing: dict, palette: str, rng):
    """Weighted colour from clothing.garment_colors[palette] -> (name, '#rrggbb')."""
    entries = clothing["garment_colors"][palette]
    name = rng.choices(list(entries), weights=[float(e["pct"]) for e in entries.values()], k=1)[0]
    return name, entries[name]["rgb"]


def _recolor_sock(path, texture_path, spec: dict, clothing: dict, rng) -> None:
    cfg = clothing.get("sock_recolor") or {}
    if Path(path).stem not in (cfg.get("assets") or []):
        return
    weights = cfg["colors"][spec["sex"]]
    name = rng.choices(list(weights), weights=[float(v) for v in weights.values()], k=1)[0]
    if name == "nude":
        r, g, b = colors.hex_to_srgb(spec["skin"].get("albedo_hex") or spec["skin"]["rgb_hex"])
        rgb = (r * 0.8, g * 0.75, b * 0.72)
    else:
        rgb = colors.hex_to_srgb(cfg["rgb"][name])
    changed = materials.recolor_neutral(texture_path, rgb, float(cfg.get("max_saturation", 0.15)),
                                        float(cfg.get("min_value", 0.55)))
    _LOG.info(f"sock of {Path(path).stem}: {name} ({changed} texture pixels)")


def add_body_parts(ns, basemesh, armature, spec: dict, appearance: dict, textures_dir: Path, report: dict) -> dict:
    used = {}
    eye_assets = _candidates(ns, "eyes") if appearance["eyes"].get("source", "generated") == "pack" else []
    if eye_assets:
        obj = _add_mhclo(ns, sorted(eye_assets, key=lambda c: c["name"])[0]["path"], basemesh, "eyes")
        materials.normalise(obj, f"{spec['id']}_eyes", textures_dir)
        used["eyes"] = obj.name
    else:
        eyes.build_eyes(basemesh, armature, spec, appearance)
        used["eyes"] = "generated"
    wanted = {"eyebrows": spec.get("eyebrows"), "eyelashes": spec.get("eyelashes"),
              "hair": None if spec["hair"]["style"] == "none" else spec["hair"]["style"]}
    for part, name in wanted.items():
        if not name:
            used[part] = None
            continue
        installed = _candidates(ns, part)
        match = next((c for c in installed if name.lower() in c["name"].lower()), None)
        if match is None:
            message = f"{part} '{name}' skipped: " + ("not found in installed assets" if installed
                                                      else "no MakeHuman asset pack installed")
            report["warnings" if installed else "notes"].append(message)
            used[part] = None
            continue
        obj = _add_mhclo(ns, match["path"], basemesh, part)
        tint = _hair_tint(appearance, spec) if part in ("hair", "eyebrows") else None
        materials.normalise(obj, f"{spec['id']}_{part}", textures_dir, alpha=True, tint_hex=tint, roughness=0.5)
        used[part] = match["name"]
    _LOG.info(f"body parts: {used}")
    return used


def _layer(worn: list, offset_m: float) -> None:
    """Keep layered garments apart: trousers / skirts go over tucked shirts, otherwise the top
    goes over the bottom. The outer garment gets a small outward Displace."""
    by_slot = {w["slot"]: w for w in worn}
    top, bottom = by_slot.get("upper_body"), by_slot.get("lower_body")
    if not top or not bottom or offset_m <= 0:
        return
    tucked = "tucked" in top["asset"] and "untucked" not in top["asset"]
    outer = bottom if tucked else top
    obj = bpy.data.objects[outer["object"]]
    modifier = obj.modifiers.new("LayerOffset", "DISPLACE")
    modifier.strength, modifier.mid_level = offset_m, 0.0
    outer["layer"] = "outer"
    _LOG.info(f"layering: {outer['asset']} is the outer garment")


def add_clothing(ns, basemesh, spec: dict, clothing: dict, textures_dir: Path, report: dict,
                 variant_name: str = None) -> list:
    """Dress the human with its clothing variant; falls back to `fallback_variant` if nothing fits."""
    variant_name = variant_name or spec["clothing_variant"]
    variant = clothing["variants"][variant_name]
    rng = random.Random(spec["seed"] ^ 0xC10)
    taken, worn = set(), []
    candidates = None
    for slot_name, configured in variant["slots"].items():
        slot = clothing_match.resolve_slot(configured, spec["sex"], rng)
        if slot is None:      # e.g. a female-only garment for a male human
            continue
        path = None
        if "asset" in slot:
            p = Path(slot["asset"])
            p = p if p.is_absolute() else ASSETS_DIR / p
            path = p if p.exists() else None
            missing = f"{slot_name}: asset {p} not found"
        else:
            candidates = candidates if candidates is not None else _candidates(ns, "clothes")
            choice = clothing_match.pick(candidates, slot["mpfb_slot"], spec["sex"], rng,
                                         clothing.get("mpfb_packs"), taken)
            path = Path(choice["path"]) if choice else None
            missing = f"{slot_name}: no installed MPFB clothes asset matches {slot['mpfb_slot']} (or chance roll)"
        if path is None:
            if clothing.get("fallback_if_missing") == "error" and "asset" in slot:
                raise FileNotFoundError(missing)
            if "asset" in slot:
                report["warnings"].append(missing)
            else:
                report["notes"].append(missing)
            continue
        obj = _add_mhclo(ns, str(path), basemesh, "Clothes")
        taken.add(str(path))
        color_name = None
        if "hospital_gown" in str(path):   # generated garments (gowns, office skirt)
            rig = basemesh.parent
            bones = {b.name for b in rig.data.bones} if rig is not None and rig.type == "ARMATURE" else None
            color = None
            if slot.get("recolor"):
                color_name, rgb = _pick_color(clothing, slot["recolor"], rng)
                color = {"rgb": rgb, "base_rgb": rgb, "pattern": "solid"}
            gown_style.style_gown(obj, spec, clothing, path, textures_dir, bones, color=color, label=slot_name)
        else:
            texture = materials.normalise(obj, f"{spec['id']}_{slot_name}", textures_dir, alpha=True, bake_colour=True,
                                          max_resolution=int(clothing.get("garment_texture_max_px", 1024)))
            if texture:
                _recolor_sock(path, textures_dir / texture, spec, clothing, rng)
                if slot.get("recolor"):
                    color_name, rgb = _pick_color(clothing, slot["recolor"], rng)
                    materials.recolor_garment(textures_dir / texture, colors.hex_to_srgb(rgb))
        worn.append({"slot": slot_name, "asset": path.stem, "object": obj.name, "variant": variant_name,
                     "color": color_name,
                     "delete_group": delete_group_name(path),
                     "hides_body": slot_name in (clothing.get("hide_body_under") or [])})
        _LOG.info(f"clothing {slot_name}: {path.stem}{f' ({color_name})' if color_name else ''}")
    _layer(worn, float(clothing.get("layer_offset_cm", 0.5)) / 100.0)
    garment_fit.resolve_poke_through(basemesh, worn, clothing)
    fallback = clothing.get("fallback_variant")
    if not worn and fallback and fallback != variant_name:
        report["notes"].append(f"clothing variant '{variant_name}' produced no garments; using '{fallback}'")
        return add_clothing(ns, basemesh, spec, clothing, textures_dir, report, fallback)
    return worn
