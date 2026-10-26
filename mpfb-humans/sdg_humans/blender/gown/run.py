"""Blender task: generate all configured gown variants (and the office skirt) as MPFB clothes assets.

Each gown = draped lower part (straight fall to the knee) + upper shell cut from the body's
torso / upper-arm faces (shoulders, neckline, trimmed short sleeves) + back opening with ties,
authored around the neutral basemesh and written with MPFB's MakeClothes services.
"""

import logging
from pathlib import Path

import bpy

from .. import bootstrap, geometry
from . import body_parts, extras, mhclo_writer, skirt, texture
from .builder import MeshBuilder
from .regions import dominant_bones

_LOG = logging.getLogger("sdg_humans.blender.gown")

_JOINTS = ("neck", "pelvis", "l-shoulder", "r-shoulder", "l-elbow", "r-elbow",
           "l-upper-leg", "r-upper-leg", "l-knee", "r-knee")


def _context(basemesh, armature) -> dict:
    coords = geometry.evaluated_coords(basemesh)
    joints = {name.replace("-", "_"): geometry.joint_centre(basemesh, coords, f"joint-{name}") for name in _JOINTS}
    return {"basemesh": basemesh, "coords": coords, "joints": joints,
            "body": geometry.group_vertex_indices(basemesh, "body"),
            "dom": dominant_bones(basemesh, {b.name for b in armature.data.bones})}


def build_gown(ctx: dict, name: str, variant: dict, cfg: dict):
    builder = MeshBuilder()
    if variant.get("type") == "skirt":
        info = skirt.build_skirt(builder, ctx, variant, cfg)
    else:
        info = body_parts.build_body(builder, ctx, variant, cfg)
        extras.build_ties(builder, info, variant, cfg)
    _LOG.debug(f"{name}: hem z={info['hem_z']:.3f} top z={info['top_z']:.3f} {len(builder.faces)} quads")
    return builder.to_object(name)


def run(args: dict) -> dict:
    cfg = args["gown_cfg"]
    out_dir = Path(args["out_dir"])
    ns = bootstrap.mpfb(args.get("mpfb_module", "auto"))
    bootstrap.clear_scene()
    # neutral basemesh, helpers visible (MakeClothes matches the skirt against helper-skirt)
    basemesh = ns.HumanService.create_human(mask_helpers=False)
    armature = ns.HumanService.add_builtin_rig(basemesh, "default", import_weights=True)
    (out_dir / "textures").mkdir(parents=True, exist_ok=True)
    texture.make_textures(out_dir / "textures", int(cfg.get("texture_size", 512)))
    ctx = _context(basemesh, armature)

    written = {}
    only = set(args.get("variants") or cfg["variants"].keys())
    for name, variant in cfg["variants"].items():
        if name not in only:
            continue
        _LOG.info(f"building gown variant {name}: {variant}")
        gown = build_gown(ctx, name, variant, cfg)
        written[name] = str(mhclo_writer.write_asset(ns, basemesh, gown, out_dir, name, cfg))
        bpy.data.objects.remove(gown, do_unlink=True)
    return {"status": "ok", "written": written}
