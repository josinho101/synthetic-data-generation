"""Build ONE human from its manifest spec and write all outputs (in-process, no Blender).

Steps (each logged with its duration):
  fit (phenotypes + face -> height solve -> mass/BMI) -> skin -> body parts -> clothing -> floor (footwear lift)
  -> landmarks -> measure -> anatomy -> skeleton -> USD -> metadata
The preview PNG is rendered by the orchestrator from the final USD (after usd_post).
"""

import json
import logging
import platform
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .. import __version__, garments, landmarks, measure, skin, textures, usd_writer
from ..anatomy.build import build_skeleton
from ..body_fit import fit_body
from ..geometry import triangulate
from ..metadata.writer import build_metadata
from ..model import usd_name
from ..proxy_fit import merge_influences

_LOG = logging.getLogger("anny_humans.build")


@contextmanager
def step(name: str, timings: dict):
    started = time.monotonic()
    _LOG.info(f"step {name} ...")
    yield
    timings[name] = round(time.monotonic() - started, 2)
    _LOG.info(f"step {name} done in {timings[name]:.2f}s")


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serialisable: {type(value)}")


def _body_item(body, rest, hid: str, removed: np.ndarray, material: dict, max_influences: int) -> dict:
    """The exported body: hm08 'body' faces (helpers dropped) minus faces touching removed vertices (in shoes)."""
    keep = body.body_mask.copy()
    keep[removed] = False
    faces = body.faces[body.body_faces]
    uv_faces = body.uv_faces[body.body_faces]
    ok = np.all(keep[np.clip(faces, 0, None)] | (faces < 0), axis=1)
    faces, uv_faces = faces[ok], uv_faces[ok]
    vertices = np.where(keep)[0]
    remap = np.full(body.vertex_count, -1, dtype=np.int64)
    remap[vertices] = np.arange(len(vertices))
    polys = [[int(remap[v]) for v in f if v >= 0] for f in faces]
    uvs = [[int(t) for t, v in zip(tf, f) if v >= 0] for tf, f in zip(uv_faces, faces)]
    idx, wt = merge_influences(body.skin_index[vertices], body.skin_weight[vertices], max_influences)
    return {"prim": hid, "mesh": "base", "points": rest.vertices[vertices], "faces": polys, "uv": body.uv,
            "uv_faces": uvs, "joint_index": idx, "joint_weight": wt, "material": material, "kind": "body",
            "vertex_ids": vertices}


def _bone_items(bones: list, joint_index: dict, material: dict, max_influences: int) -> list:
    items = []
    for entry in bones:
        n = len(entry["points"])
        k = max(1, min(max_influences, max(len(w) for w in entry["weights"])))
        idx, wt = np.zeros((n, k), dtype=np.int64), np.zeros((n, k))
        for v, weights in enumerate(entry["weights"]):
            top = sorted(weights.items(), key=lambda t: -t[1])[:k]
            total = sum(w for _, w in top) or 1.0
            for c, (bone, w) in enumerate(top):
                idx[v, c], wt[v, c] = joint_index[bone], w / total
        name = f"bone_{entry['name']}"
        items.append({"prim": name, "mesh": name, "points": entry["points"], "faces": entry["tris"].tolist(),
                      "uv": None, "uv_faces": None, "joint_index": idx, "joint_weight": wt, "material": material,
                      "kind": "bone"})
    return items


def build_human(body, catalogue: dict, cfg: dict, spec: dict, human_dir: Path, run_id: str, assets_dir) -> dict:
    hid = spec["id"]
    human_dir = Path(human_dir)
    textures_dir = human_dir / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)
    timings, report = {}, {"warnings": [], "notes": []}
    usd_cfg = cfg["export"]["usd"]
    k = int(usd_cfg.get("max_bone_influences", 4))

    with step("fit", timings):
        local_changes, skipped = body.face_target_changes(spec["face_targets"], catalogue)
        if skipped:
            report["notes"].append(f"{len(skipped)} face targets have no Anny local change: {skipped[:5]}")
        rest, fit = fit_body(body, spec, local_changes, cfg["population"], cfg["body"])
        if not fit["fit_ok"]:
            report["warnings"].append(f"fit not exact: {fit}")
    with step("skin", timings):
        skin_info = skin.build_skin(spec, cfg["appearance"], assets_dir, textures_dir, report)
    with step("body_parts", timings):
        part_items, parts = garments.add_body_parts(body, rest, spec, cfg["appearance"], assets_dir, textures_dir,
                                                    report, k)
    with step("clothing", timings):
        cloth_items, clothing = garments.add_clothing(body, rest, spec, cfg["clothing"], assets_dir, textures_dir,
                                                      report, k)
    with step("floor", timings):   # shoe soles on z = 0
        lowest = min([0.0] + [float(np.min(i["points"][:, 2])) for i in cloth_items + part_items])
        lift = -lowest if lowest < -0.001 else 0.0
        if lift:
            rest = rest.translated([0.0, 0.0, lift])
            for item in cloth_items + part_items:
                item["points"] = item["points"] + np.array([0.0, 0.0, lift])
            _LOG.info(f"lifted {lift * 100:.1f} cm so the footwear stands on the floor")
        fit["footwear_lift_cm"] = round(lift * 100.0, 2)
    with step("landmarks", timings):
        body_tris = body.triangles(body.body_faces)
        points, spine_shape = landmarks.compute_landmarks(rest.vertices, body.body_vertices, body_tris,
                                                          cfg["landmarks"], {"seed": spec["seed"],
                                                                             "age": spec["age_years"]})
        lm_names, lm_parents, lm_world, lm_meta = landmarks.to_joints(points, cfg["landmarks"], body.bone_labels,
                                                                      rest.heads, rest.tails)
    with step("measure", timings):
        measurements = measure.measure(body, rest.vertices, lm_meta, cfg["landmarks"])
    bones = []
    if cfg["anatomy"].get("enabled", True):
        with step("anatomy", timings):
            eyes = [(i["points"], triangulate(i["faces"])) for i in part_items if i["kind"] == "eyes"]
            bones = build_skeleton(body, rest, lm_meta, cfg["landmarks"]["spine"]["levels"],
                                   fit["height_cm"] / 100.0, cfg["anatomy"], eyes)
    with step("skeleton", timings):
        root = (cfg["export"].get("usd_post") or {}).get("root_joint") or None
        offset = 1 if root else 0
        rig_names = list(body.joint_names)
        names = ([root] if root else []) + rig_names + lm_names
        parents = ([-1] if root else []) + [(p + offset) if p >= 0 else (0 if root else -1)
                                             for p in body.bone_parents] + [p + offset for p in lm_parents]
        world = np.concatenate(([np.eye(4)[None]] if root else []) + [rest.world, lm_world.reshape(-1, 4, 4)])
        paths = usd_writer.joint_paths(names, parents)
        for (name, info), joint_path in zip(lm_meta.items(), paths[offset + len(rig_names):]):
            info["usd_joint"] = joint_path
        joint_index = {label: i + offset for i, label in enumerate(body.bone_labels)}
        removed = garments.hide_body_under(body, rest, cloth_items, clothing)
        body_material = {"name": f"{hid}_skin", "kind": "skin", "diffuse": skin_info["texture"],
                         "color": skin_info["albedo_linear"], "roughness": skin_info["roughness"],
                         "normal": skin_info["normal"], "roughness_map": skin_info["roughness_map"],
                         "subsurface": skin_info["subsurface"]}
        items = [_body_item(body, rest, hid, removed, body_material, k)] + part_items + cloth_items
        for item in items:
            item["joint_index"] = np.asarray(item["joint_index"]) + offset
        bone_color = [float(c) for c in textures.srgb_to_linear(textures.hex_to_srgb(cfg["anatomy"].get("color_rgb", "#e3d8c3")))]
        bone_material = {"name": f"{hid}_bone", "kind": "bone", "color": bone_color, "roughness": 0.6}
        items += _bone_items(bones, joint_index, bone_material, k)
    ext = usd_cfg.get("file_format", "usd")
    usd_path = human_dir / f"{hid}.{ext}"
    with step("usd", timings):
        custom = {"id": hid, "sex": spec["sex"], "ethnicity": spec["ethnicity"], "age_years": spec["age_years"],
                  "skin_tone_mst": spec["skin"]["tone_mst"], "height_cm": fit["height_cm"],
                  "weight_kg": fit["weight_kg"], "bmi": fit["bmi"], "generator": f"anny-humans {__version__}"}
        usd_info = usd_writer.write_human(usd_path, hid, names, parents, world, items, usd_cfg, custom)
    rig_prim = f"/{hid}/{hid}_rig"
    anatomy_meta = [{"name": b["name"], "object": f"bone_{b['name']}", "rig_bone": b["rig_bone"], "part": b["part"],
                     "vertices": int(len(b["points"])), "usd_prim": f"{rig_prim}/bone_{b['name']}/bone_{b['name']}"}
                    for b in bones]
    with step("metadata", timings):
        skeleton = {"rig": f"anny_{body.rig}", "bone_count": len(names), "deform_bone_count": len(rig_names),
                    "landmark_joint_count": sum(1 for v in lm_meta.values() if v["kind"] != "frame"),
                    "frame_joint_count": sum(1 for v in lm_meta.values() if v["kind"] == "frame"),
                    "root_joint": root, "usd_root_prim": f"/{hid}", "usd_skeleton_prim": usd_info["usd_skeleton_prim"]}
        for entry in clothing:
            entry["usd_prim"] = f"{rig_prim}/{usd_name(entry['object'])}"
        files = {"usd": usd_path.name, "preview": f"{hid}.png", "metadata": f"{hid}.json",
                 "textures": sorted(p.name for p in textures_dir.glob("*.png"))}
        skin_meta = {k_: v for k_, v in skin_info.items() if k_ not in ("albedo_linear",)}
        build = {"fit": fit, "measurements": measurements, "skin": skin_meta, "body_parts": parts,
                 "clothing": clothing, "skeleton": skeleton, "landmarks": lm_meta, "spine_shape": spine_shape,
                 "anatomy": anatomy_meta, "files": files, "warnings": report["warnings"], "notes": report["notes"]}
        versions = {"anny": body.version, "generator": __version__, "python": platform.python_version(),
                    "device": body.device}
        meta = build_metadata(spec, run_id, build, versions)
        meta["anny_local_changes"] = {k_: round(v, 4) for k_, v in sorted(local_changes.items())}
        (human_dir / f"{hid}.json").write_text(json.dumps(meta, indent=2, default=_json_default), encoding="utf-8")
    status = "warn" if report["warnings"] else "ok"
    for warning in report["warnings"]:
        _LOG.warning(warning)
    for note in report["notes"]:
        _LOG.info(f"note: {note}")
    return {"status": status, "id": hid, "height_cm": fit["height_cm"], "weight_kg": fit["weight_kg"],
            "bmi": fit["bmi"], "fit_ok": fit["fit_ok"], "warnings": report["warnings"], "notes": report["notes"],
            "timings": timings, "usd": str(usd_path)}
