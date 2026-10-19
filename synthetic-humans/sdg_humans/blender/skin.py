"""Skin: MPFB material (layered procedural or system mhmat) tinted to the sampled tone, then baked."""

import logging

import bpy

from . import bake, colors

_LOG = logging.getLogger("sdg_humans.blender.skin")

_SKIN_GROUPS = ("bodygroup", "facegroup", "earsgroup")


def find_system_skin(ns, base_skin: str):
    """Best matching MakeHuman system skin .mhmat for e.g. 'young caucasian female'."""
    try:
        candidates = ns.AssetService.list_mhmat_assets("skins")
    except Exception:  # noqa: BLE001
        return None
    words = base_skin.lower().split()
    scored = sorted(((sum(w in str(p).lower() for w in words), str(p)) for p in candidates), reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 2 else None


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


def _tint_mhmat(material, rgba) -> None:
    """Multiply the diffuse texture of a MakeSkin material by the tone colour."""
    tree = material.node_tree
    bsdf = next((n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None or not bsdf.inputs["Base Color"].links:
        return
    source = bsdf.inputs["Base Color"].links[0].from_socket
    mix = tree.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.85
    tree.links.new(source, mix.inputs["A"])
    mix.inputs["B"].default_value = colors.scale_rgba(rgba, (1.6, 1.6, 1.6))
    tree.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])


def apply_skin(ns, basemesh, spec: dict, appearance: dict, asset_report: dict) -> dict:
    skin_cfg = appearance["skin"]
    source = skin_cfg.get("source", "auto")
    mhmat = find_system_skin(ns, spec["skin"]["base_skin"]) if source in ("auto", "mhmat") else None
    if source == "mhmat" and not mhmat:
        asset_report["warnings"].append("skin.source=mhmat but no system skin found; using layered skin")
    rgba = colors.hex_to_linear_rgba(spec["skin"]["rgb_hex"])
    if mhmat:
        ns.HumanService.set_character_skin(mhmat, basemesh, skin_type="MAKESKIN", material_instances=False)
        _tint_mhmat(basemesh.active_material, rgba)
        used = f"mhmat:{mhmat}"
    else:
        ns.HumanService.set_character_skin(None, basemesh, skin_type="LAYERED")
        _tint_layered(basemesh.active_material, rgba)
        used = "layered"
    _LOG.info(f"skin source {used}, tone MST {spec['skin']['tone_mst']} {spec['skin']['rgb_hex']}")
    return {"source": used}


def bake_skin(basemesh, textures_dir, human_id: str, appearance: dict) -> str:
    skin_cfg = appearance["skin"]
    path = bake.bake_diffuse_color(basemesh, textures_dir / f"{human_id}_skin.png",
                                   int(skin_cfg.get("bake_resolution", 2048)))
    material = bake.simple_material(f"{human_id}_skin", image_path=path,
                                    roughness=float(skin_cfg.get("roughness", 0.45)))
    bake.replace_materials(basemesh, material)
    return path.name
