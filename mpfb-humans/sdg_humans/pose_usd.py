"""USD side of the exam posing (pxr): read a human's skeleton, write the exam poses as a UsdSkelAnimation.

Shared verbatim by the MPFB (mpfb-humans) and MHR (mhr-synthetic-human) pipelines.

    run(human_usd, poses_cfg, out_path)  -> report dict (also written next to out_path as .json)

The output layer references the human unchanged and adds /World/<id>/<rig>/ExamPoses with one time
sample per pose (time code = index in the report's "poses" list), bound as the skeleton's animation.
"""

import json
import os
from pathlib import Path

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdSkel, Vt

from . import pose_rules as pr


def _skeleton(stage):
    for prim in stage.Traverse():
        if prim.IsA(UsdSkel.Skeleton):
            return UsdSkel.Skeleton(prim)
    raise RuntimeError("no UsdSkel Skeleton in the human USD")


def load(human_usd):
    stage = Usd.Stage.Open(str(human_usd))
    skel = _skeleton(stage)
    joints = list(skel.GetJointsAttr().Get())
    parents = list(UsdSkel.Topology(joints).GetParentIndices())
    rest = np.array([np.array(m).T for m in skel.GetRestTransformsAttr().Get()])   # USD rows -> columns
    names = [j.split("/")[-1] for j in joints]
    return stage, skel, joints, pr.Skeleton(names, parents, rest)


def write_animation(human_usd: Path, stage_src, skel_src, joints, poses: list, out_path: Path) -> Path:
    default = stage_src.GetDefaultPrim()
    rel_skel = skel_src.GetPrim().GetPath().MakeRelativePath(default.GetPath())
    if out_path.exists():
        out_path.unlink()
    stage = Usd.Stage.CreateNew(str(out_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(max(len(poses) - 1, 0))
    stage.SetTimeCodesPerSecond(1)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    human = UsdGeom.Xform.Define(stage, f"/World/{default.GetName()}")
    human.GetPrim().GetReferences().AddReference(os.path.relpath(human_usd, out_path.parent))
    skel_path = human.GetPath().AppendPath(rel_skel)
    anim = UsdSkel.Animation.Define(stage, skel_path.GetParentPath().AppendChild("ExamPoses"))
    UsdSkel.BindingAPI.Apply(stage.OverridePrim(skel_path)).CreateAnimationSourceRel().SetTargets([anim.GetPath()])
    anim.CreateJointsAttr(Vt.TokenArray(joints))
    anim.CreateScalesAttr(Vt.Vec3hArray([Gf.Vec3h(1, 1, 1)] * len(joints)))
    t_attr, r_attr = anim.CreateTranslationsAttr(), anim.CreateRotationsAttr()
    for time, (name, local) in enumerate(poses):
        mats = [Gf.Matrix4d(m.T.tolist()) for m in local]
        t_attr.Set(Vt.Vec3fArray([Gf.Vec3f(m.ExtractTranslation()) for m in mats]), time)
        r_attr.Set(Vt.QuatfArray([Gf.Quatf(Gf.Matrix4d(m).RemoveScaleShear().ExtractRotationQuat()) for m in mats]),
                   time)
    anim.GetPrim().SetCustomDataByKey("exam_poses", Vt.StringArray([name for name, _ in poses]))
    stage.GetRootLayer().Save()
    return out_path


def run(human_usd, cfg: dict, out_path, pose_names=None) -> dict:
    human_usd, out_path = Path(human_usd), Path(out_path)
    stage, skel_prim, joints, skel = load(human_usd)
    rig = pr.expand_rig(cfg["rig"], cfg["side_tokens"])
    rom = {k: tuple(v) for k, v in (cfg.get("rom") or pr.ROM).items()}
    stature = float(skel.rest_world[skel.index["LM_vertex"]][2, 3])
    names = pose_names or list(pr.EXAM_POSES)
    report = {"human": human_usd.name, "rig": cfg.get("rig_name", ""), "stature_m": round(stature, 4),
              "rom_deg": {k: list(v) for k, v in rom.items()},
              "rest_angles": pr.clinical(pr.angles(skel.rest_world, skel), pr.angles(skel.rest_world, skel)),
              "poses": []}
    frames = []
    for name in names:
        result = pr.pose(skel, rig, stature, pr.EXAM_POSES[name], rom)
        frames.append((name, result["local"]))
        report["poses"].append({
            "name": name, "angles": result["angles"], "violations": result["violations"], "stats": result["stats"],
            "joints_world_m": {n: [round(float(c), 5) for c in result["world"][i][:3, 3]]
                               for i, n in enumerate(skel.names)},
            "frames_axes": {n: np.round(result["world"][i][:3, :3].T, 4).tolist()
                            for i, n in enumerate(skel.names) if n.startswith("AN_")}})
    write_animation(human_usd, stage, skel_prim, joints, frames, out_path)
    out_path.with_suffix(".json").write_text(json.dumps(report, indent=1))
    return report
