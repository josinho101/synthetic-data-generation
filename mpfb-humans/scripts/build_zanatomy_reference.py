#!/usr/bin/env python3
"""Build the Z-Anatomy reference package for the 'zanatomy' skeletal layer (one time).

    .venv/bin/python scripts/build_zanatomy_reference.py [--spike-out DIR] [--out assets/zanatomy] [--rebuild-spike]

Input: the outputs of the Z-Anatomy research spike (../zanatomy-humans/spike, see its REPORT.md):
s2_joints.json (joint centres + bony landmarks), s8_bone_points.npz (containment samples), s9_ref.npz (S3 anatomical
rig, bone meshes and the S4 reference skin fitted around them). With --rebuild-spike (or when they are missing) the
spike is re-run first (spike/run_spike.sh, needs Blender + MPFB + the Anny venv, ~15 min).

Output (CC BY-SA 4.0, gitignored): reference.npz + maps.json + manifest.json + ATTRIBUTION.md. Everything the runtime
needs is baked in, so the pipeline never imports the spike code.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent
ZA = REPO / "zanatomy-humans"
SPIKE_OUT = REPO / "output" / "zanatomy-humans" / "spike"
VERSION = "zanatomy-ref-1"
NEEDED = ("s2_joints.json", "s8_bone_points.npz", "s9_ref.npz")
SPINE = [f"L{i}" for i in range(5, 0, -1)] + [f"T{i}" for i in range(12, 0, -1)] + [f"C{i}" for i in range(7, 0, -1)]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spike-out", type=Path, default=SPIKE_OUT)
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "zanatomy")
    ap.add_argument("--rebuild-spike", action="store_true")
    a = ap.parse_args()
    src = a.spike_out
    if a.rebuild_spike or not all((src / n).exists() for n in NEEDED):
        print("[reference] running the Z-Anatomy spike (S1-S4, S8a, S9a) ...")
        subprocess.run(["bash", str(ZA / "spike" / "run_spike.sh")], check=True)
        subprocess.run(["blender", "-b", str(src / "s3_rig.blend"), "--python", str(ZA / "spike" / "s8_dump_bones.py")],
                       check=True)
        subprocess.run(["blender", "-b", str(src / "s4_mpfb.blend"), "--python", str(ZA / "spike" / "s9a_export_ref.py")],
                       check=True)
    sys.path.insert(0, str(ZA / "spike"))
    sys.path.insert(0, str(ZA))
    import defs                                                     # noqa: E402 - build time only
    from zanatomy_humans.mesh_sources import load_map              # noqa: E402

    ref = np.load(src / "s9_ref.npz")
    s2 = json.loads((src / "s2_joints.json").read_text())
    bp = np.load(src / "s8_bone_points.npz")
    names = [str(x) for x in ref["bone_names"]]
    B = defs.bones()
    assert set(B) == set(names) and all(p < i for i, p in enumerate(ref["parent"])), "rig differs from defs.bones()"
    J = {k: np.array(v["p"]) for k, v in s2["joints"].items()}
    front = np.array(s2["front"])
    skin = ref["skin_v"]

    # bone that carries each joint / landmark (head joints -> their bone, others -> the bone of the mesh they're on)
    mesh_bone = {m: bn for bn, b in B.items() for m in b["meshes"]}
    mesh_bone.update({m: bone for bone, ms in defs.TEETH_OBJECTS.values() for m in ms})
    spec = defs.joints()

    def owner_of(j):
        for bn, b in B.items():
            if b["head"] == j:
                return bn
        sp = spec[j]
        if sp["m"] == "mid":
            return owner_of(sp["of"][0])
        return mesh_bone[(sp.get("mesh") or [sp.get("a")])[0]]

    pt_names, pt_bone, pt_rest = [], [], []
    for j in J:
        try:
            pt_bone.append(names.index(owner_of(j)))
        except (KeyError, ValueError):
            continue
        pt_names.append(j)
        pt_rest.append(J[j])

    # rig joints (bone heads and tails) with a ring of reference-skin vertices each (skin-anchored joint prior)
    joint_names = sorted({b[k] for b in B.values() for k in ("head", "tail")})
    big = ("iv_", "lumbosacral", "atlanto", "costovertebral", "pelvis", "hip", "sacrum")
    rings = np.full((len(joint_names), 80), -1, dtype=np.int32)
    for i, j in enumerate(joint_names):
        k = 80 if j.startswith(big) else 40
        d = np.linalg.norm(skin - J[j], axis=1)
        rings[i, :k] = np.argsort(d)[:k]
    jt = [(names.index(bn), B[bn]["head"]) for bn in names] + [(names.index(bn), B[bn]["tail"]) for bn in names]

    # surface landmarks: reference skin vertex set (selected as in the spike), tissue depth, owner bone
    lm_cfg = json.loads((ZA / "configs" / "surface_landmarks.json").read_text())
    stomion = json.loads((ZA / "configs" / "mesh_maps" / "anny.json").read_text())["skin_points"]["stomion"]

    def direction(name, d):
        sx = -1.0 if name.endswith("_r") else 1.0
        return {"front": front, "back": -front, "up": np.array([0, 0, 1.0]), "down": np.array([0, 0, -1.0]),
                "lateral": np.array([sx, 0, 0.0]), "medial": np.array([-sx, 0, 0.0])}[d]

    rad, reach = lm_cfg["radius_mm"] / 1e3, lm_cfg["search_mm"] / 1e3
    landmarks = []
    for lm in lm_cfg["landmarks"]:
        for nm in ([lm["at"].replace("{s}", s) for s in "lr"] if "{s}" in lm["at"] else [lm["at"]]):
            if lm.get("src") == "stomion":
                idx = list(stomion)
            else:
                d = direction(nm, lm["dir"])
                rel = skin - J[nm]
                t = rel @ d
                perp = np.linalg.norm(rel - np.outer(t, d), axis=1)
                ok = np.where((perp < rad) & (np.abs(t) < reach))[0]
                if not len(ok):
                    continue
                idx = [int(ok[np.argmin(np.abs(t[ok] - lm["tissue_mm"] / 1e3) + 0.5 * perp[ok])])]
            landmarks.append({"name": nm, "bone": names.index(owner_of(nm)), "rest": J[nm].tolist(),
                              "skin_vertices": idx, "tissue_mm": lm["tissue_mm"]})

    bp_names = [str(x) for x in bp["names"]]
    samp_bone = np.array([names.index("skull" if bp_names[i] == "skull_vault" else bp_names[i]) for i in bp["bone"]])

    out = {"bone_names": np.array(names), "parent": ref["parent"], "rest_frames": ref["mat"],
           "ref_skin": skin, "ref_skin_faces": ref["skin_f"], "front": front,
           "joint_names": np.array(joint_names), "joint_rest": np.array([J[j] for j in joint_names]),
           "joint_rings": rings, "rig_joint_bone": np.array([b for b, _ in jt]),
           "rig_joint_index": np.array([joint_names.index(j) for _, j in jt]),
           "point_names": np.array(pt_names), "point_bone": np.array(pt_bone), "point_rest": np.array(pt_rest),
           "sample_points": bp["points"], "sample_bone": samp_bone, "sample_min_depth_m": bp["min_depth_m"],
           "meshes": ref["meshes"]}
    for key in [str(x) for x in ref["meshes"]]:
        for suffix in ("v", "f", "owner"):
            out[f"mesh_{key}_{suffix}"] = ref[f"mesh_{key}_{suffix}"]
    a.out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out / "reference.npz", **out)

    amap = load_map(ZA, "anny")                    # MakeHuman joint (USD name) -> anatomical bone
    pairs = [[names.index(n), names.index(n[:-1] + "R")] for n in names if n.endswith("_L") and n[:-1] + "R" in names]
    maps = {"version": VERSION,
            "weights": amap["weights"], "weights_default": amap.get("weights_default", "skull"),
            "spine_split": amap["spine_split"], "spine_order": SPINE,
            "landmarks": landmarks, "lr_pairs": pairs,
            "chains": [[names.index(f"vertebra_{v}") for v in defs.VERTEBRAE]]
                      + [[names.index(f"rib{i}_{S}") for i in range(1, 13)] for S in "LR"],
            "reference_stature_m": float(skin[:, 2].max() - skin[:, 2].min()),
            "fit_bone_prefix": "bone_"}
    (a.out / "maps.json").write_text(json.dumps(maps, indent=1))
    (a.out / "ATTRIBUTION.md").write_text((ZA / "assets" / "z-anatomy" / "ATTRIBUTION.md").read_text())
    manifest = {"version": VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                "source": {"spike_outputs": str(src), "inputs_sha256": {n: sha256(src / n) for n in NEEDED},
                           "z_anatomy_fbx_sha256": (ZA / "assets" / "z-anatomy" / "SHA256SUMS").read_text().split()},
                "license": "CC-BY-SA-4.0 (bone meshes, Z-Anatomy / BodyParts3D)",
                "files": {n: sha256(a.out / n) for n in ("reference.npz", "maps.json")},
                "counts": {"bones": len(names), "meshes": len(ref["meshes"]), "landmarks": len(landmarks),
                           "joints": len(joint_names), "samples": int(len(samp_bone))}}
    (a.out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"[reference] {VERSION} -> {a.out}: {manifest['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
