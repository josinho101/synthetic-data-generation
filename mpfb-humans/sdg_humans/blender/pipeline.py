"""Blender task 'build': create ONE human from its manifest spec and write all outputs.

Steps (each logged with its duration):
  body -> face -> fit -> skin -> bake -> rig -> body parts -> clothing
       -> landmarks -> measure -> [anatomy | skeleton body dump] -> preview -> USD export -> metadata

The skeletal layer (configs/skeleton.yaml, sdg_humans/skeleton) decides the bone step: 'procedural' builds the bone
meshes here; a host-side layer such as 'zanatomy' only gets the closed body saved for it and does its work on the
exported USD afterwards.
"""

import logging
import time
from contextlib import contextmanager
from pathlib import Path

import bpy

from ..metadata.writer import build_metadata, write_metadata
from ..skeleton import get_layer
from . import assets, bake, body, bootstrap, fit, landmarks, measure, preview, rig, skeleton_dump, skin, usd_export
from .anatomy import build as anatomy

_LOG = logging.getLogger("sdg_humans.blender.pipeline")


@contextmanager
def step(name: str, timings: dict):
    started = time.monotonic()
    _LOG.info(f"step {name} ...")
    yield
    timings[name] = round(time.monotonic() - started, 2)
    _LOG.info(f"step {name} done in {timings[name]:.2f}s")


def _skeleton_info(armature, human_id: str, lm_result: dict, skeleton_prim: str) -> dict:
    return {"rig": "mpfb_default", "bone_count": len(armature.data.bones),
            "deform_bone_count": sum(1 for b in armature.data.bones if b.use_deform),
            "landmark_joint_count": sum(1 for v in lm_result.values() if v["kind"] != "frame"),
            "frame_joint_count": sum(1 for v in lm_result.values() if v["kind"] == "frame"),
            "usd_root_prim": f"/{human_id}",
            "usd_skeleton_prim": skeleton_prim}


def run(args: dict) -> dict:
    cfg, spec = args["config"], args["spec"]
    human_dir = Path(args["human_dir"])
    textures = human_dir / "textures"
    textures.mkdir(parents=True, exist_ok=True)
    timings, report = {}, {"warnings": [], "notes": []}
    hid = spec["id"]

    ns = bootstrap.mpfb(cfg["export"].get("mpfb_module", "auto"))
    bootstrap.clear_scene()
    bake.configure_cycles(cfg["export"]["bake"].get("device", "auto"), int(cfg["export"]["bake"].get("samples", 4)))

    with step("body", timings):
        basemesh = body.create_body(ns, spec)
    with step("face", timings):
        body.apply_face_targets(ns, basemesh, spec["face_targets"])
    with step("fit", timings):
        fit_result = fit.fit_body(ns, basemesh, spec, cfg["population"])
        if not fit_result["fit_ok"]:
            report["warnings"].append(f"fit not exact: {fit_result}")
    with step("skin", timings):
        skin_info = skin.apply_skin(ns, basemesh, spec, cfg["appearance"], report)
    with step("bake", timings):
        skin_info["texture"], skin_info["tone"] = skin.bake_skin(basemesh, textures, hid, cfg["appearance"],
                                                                 spec["skin"].get("albedo_lab"))
    with step("rig", timings):
        armature = rig.add_default_rig(ns, basemesh)
    with step("body_parts", timings):
        parts = assets.add_body_parts(ns, basemesh, armature, spec, cfg["appearance"], textures, report)
    with step("clothing", timings):
        clothing = assets.add_clothing(ns, basemesh, spec, cfg["clothing"], textures, report,
                                       catalog=cfg.get("garment_catalog"))
    with step("floor", timings):
        lift_m = rig.lift_to_floor(armature)
        fit_result["footwear_lift_cm"] = round(lift_m * 100.0, 2)
    with step("landmarks", timings):
        points, spine_shape = landmarks.compute_landmarks(basemesh, cfg["landmarks"],
                                                          {"seed": spec["seed"], "age": spec["age_years"]})
        lm_result = landmarks.add_landmark_bones(armature, points, cfg["landmarks"])
    with step("measure", timings):
        measurements = measure.measure(basemesh, lm_result, cfg["landmarks"])
    bones, layer, dump = [], get_layer(cfg), None
    if layer.needs_body_dump:
        with step("skeleton_dump", timings):
            dump = skeleton_dump.dump_body(basemesh, Path(args["work_dir"]) / "skeleton_body.npz", fit_result, spec)
    if layer.builds_in_blender and cfg["anatomy"].get("enabled", True):
        with step("anatomy", timings):
            bones = anatomy.build_skeleton(basemesh, armature, lm_result, cfg["landmarks"]["spine"]["levels"],
                                           fit_result["height_cm"] / 100.0, cfg["anatomy"], hid)
    with step("finalize", timings):   # before the preview, so the PNG shows exactly what is exported
        usd_export.finalize_basemesh(ns, basemesh, [c["delete_group"] for c in clothing if c.get("hides_body")],
                                     [bpy.data.objects[c["object"]] for c in clothing if c.get("hides_body")])
    with step("preview", timings):
        preview_path = preview.render_preview(human_dir / f"{hid}.png", fit_result["height_cm"] / 100.0,
                                              cfg["export"]["preview"], lm_result)
        if bones and cfg["anatomy"].get("preview", True):
            anatomy.render_skeleton_preview(human_dir / f"{hid}_skeleton.png", fit_result["height_cm"] / 100.0,
                                            cfg["export"]["preview"], bones)
    ext = cfg["export"]["usd"].get("file_format", "usd")
    with step("usd_export", timings):
        usd_path = usd_export.export_usd(armature, human_dir / f"{hid}.{ext}", hid, cfg["export"]["usd"])
    skeleton_prim = f"/{hid}/{usd_export.usd_name(armature.name)}/{usd_export.usd_name(armature.name)}"
    for name, info in lm_result.items():
        info["usd_joint"] = usd_export.joint_path(armature.data.bones[info["bone"]])
    rig_prim = f"/{hid}/{usd_export.usd_name(armature.name)}"
    for entry in bones:
        name = usd_export.usd_name(entry["object"])
        entry["usd_prim"] = f"{rig_prim}/{name}/{name}"

    with step("metadata", timings):
        files = {"usd": usd_path.name, "preview": preview_path.name, "metadata": f"{hid}.json",
                 "skeleton_preview": f"{hid}_skeleton.png" if bones and cfg["anatomy"].get("preview", True) else None,
                 "textures": sorted(p.name for p in textures.glob("*.png"))}
        build = {"fit": fit_result, "measurements": measurements, "skin": skin_info, "body_parts": parts,
                 "clothing": clothing, "skeleton": _skeleton_info(armature, hid, lm_result, skeleton_prim),
                 "landmarks": lm_result, "spine_shape": spine_shape, "anatomy": bones, "files": files, "warnings": report["warnings"],
                 "notes": report["notes"]}
        versions = {"blender": bpy.app.version_string, "mpfb": bootstrap.mpfb_version(ns),
                    "generator": args.get("generator_version", "unknown")}
        write_metadata(human_dir / f"{hid}.json", build_metadata(spec, args["run_id"], build, versions))

    status = "warn" if report["warnings"] else "ok"
    for warning in report["warnings"]:
        _LOG.warning(warning)
    for note in report["notes"]:
        _LOG.info(f"note: {note}")
    return {"status": status, "id": hid, "height_cm": fit_result["height_cm"], "weight_kg": fit_result["weight_kg"],
            "bmi": fit_result["bmi"], "fit_ok": fit_result["fit_ok"], "warnings": report["warnings"],
            "notes": report["notes"],
            "timings": timings, "usd": str(usd_path), "skeleton_body": dump["path"] if dump else None}
