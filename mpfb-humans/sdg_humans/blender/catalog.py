"""Blender task 'catalog': render every garment of garment_catalog.yaml on a reference human (visual QA).

One reference human per sex (from the manifest sampler) is built once: body, face, fit, baked skin (as exported),
rig, eyes / hair. Each garment is then added with the same MHCLO fit as the pipeline (assets._add_mhclo), keeping
the asset's own MakeHuman material (diffuse + normal / specular maps where the asset has them), rendered front + side
with the preview renderer, and removed again before the next garment.
"""

import logging
from pathlib import Path

import bpy

from . import assets, bake, bootstrap, body, fit, preview, rig, skin

_LOG = logging.getLogger("sdg_humans.blender.catalog")


def _reference_human(ns, cfg: dict, spec: dict, work_dir: Path, report: dict):
    bootstrap.clear_scene()
    basemesh = body.create_body(ns, spec)
    body.apply_face_targets(ns, basemesh, spec["face_targets"])
    height_m = fit.fit_body(ns, basemesh, spec, cfg["population"])["height_cm"] / 100.0
    skin.apply_skin(ns, basemesh, spec, cfg["appearance"], report)
    skin.bake_skin(basemesh, work_dir, f"ref_{spec['sex']}", cfg["appearance"], spec["skin"].get("albedo_lab"))
    armature = rig.add_default_rig(ns, basemesh)
    assets.add_body_parts(ns, basemesh, armature, spec, cfg["appearance"], work_dir, report)
    return basemesh, height_m


def _render_garment(ns, basemesh, path: str, out_png: Path, height_m: float, preview_cfg: dict) -> None:
    modifiers = {m.name for m in basemesh.modifiers}
    obj = assets._add_mhclo(ns, path, basemesh, "Clothes")
    try:
        preview.render_preview(out_png, height_m, preview_cfg)
    finally:
        for modifier in [m for m in basemesh.modifiers if m.name not in modifiers]:   # delete-group masks
            basemesh.modifiers.remove(modifier)
        bpy.data.objects.remove(obj, do_unlink=True)


def run(args: dict) -> dict:
    cfg, out_dir = args["config"], Path(args["out_dir"])
    tiles_dir, work_dir = out_dir / "tiles", out_dir / "_work"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    preview_cfg = dict(cfg["export"]["preview"], landmark_overlay=False, resolution=args.get("resolution", [384, 576]),
                       engines=args.get("engines", ["CYCLES"]))
    ns = bootstrap.mpfb(cfg["export"].get("mpfb_module", "auto"))
    bake.configure_cycles(cfg["export"]["bake"].get("device", "auto"), int(cfg["export"]["bake"].get("samples", 4)))
    installed = {c["name"]: c["path"] for c in assets._candidates(ns, "clothes")}
    report = {"warnings": [], "notes": []}
    tiles, failed = {}, {}
    scene = bpy.context.scene
    scene.cycles.samples, scene.cycles.use_denoising = int(args.get("samples", 32)), True   # used when engine = CYCLES
    for sex, spec in args["specs"].items():
        wanted = [g for g in args["garments"] if g["sex"] in (sex, "any")]
        if not wanted:
            continue
        basemesh, height_m = _reference_human(ns, cfg, spec, work_dir, report)
        out_png = tiles_dir / f"_nude_{sex}.png"
        preview.render_preview(out_png, height_m, preview_cfg)
        tiles[f"_nude_{sex}"] = str(out_png)
        for garment in wanted:
            key = f"{garment['id']}_{sex}"
            if garment["asset"] not in installed:
                failed[key] = "not installed"
                continue
            try:
                out_png = tiles_dir / f"{key}.png"
                _render_garment(ns, basemesh, installed[garment["asset"]], out_png, height_m, preview_cfg)
                tiles[key] = str(out_png)
                _LOG.info(f"catalog {key}: {garment['asset']}")
            except Exception as exc:  # noqa: BLE001 - one broken asset must not stop the catalogue
                failed[key] = f"{type(exc).__name__}: {exc}"
                _LOG.warning(f"catalog {key} failed: {exc}")
    return {"status": "warn" if failed else "ok", "tiles": tiles, "failed": failed, "notes": report["notes"]}
