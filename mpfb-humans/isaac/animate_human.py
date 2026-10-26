#!/usr/bin/env python3
"""Create an animated Isaac Sim scene for a generated human (pxr only: usd-core or Isaac's Python).

    python isaac/animate_human.py <run>/humans/H0001/H0001.usd                # -> H0001_anim.usda
    python isaac/animate_human.py H0001.usd --out scene.usda --walk-distance 4 --fps 30

The output layer references the human unchanged and adds:
  * /World/<id>                        Xform with animated translate (walk path, jump) + rotateZ (turns)
  * /World/<id>/<rig>/Anim             UsdSkelAnimation: idle -> walk -> idle -> jump -> turn ->
                                       walk back -> turn -> idle (procedural, see motion.py)
  * skel:animationSource on the Skeleton
Open it in Isaac Sim and press Play. Landmark joints (LM_*) and bone meshes follow the motion.
"""

import argparse
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel, Vt  # noqa: E402

import motion  # noqa: E402

AXES = {"X": Gf.Vec3d(1, 0, 0), "Y": Gf.Vec3d(0, 1, 0), "Z": Gf.Vec3d(0, 0, 1)}
CONTACT_JOINTS = ("foot_L", "foot_R", "toe1_1_L", "toe1_1_R", "toe5_1_L", "toe5_1_R")


def _skeleton(stage):
    for prim in stage.Traverse():
        if prim.IsA(UsdSkel.Skeleton):
            return UsdSkel.Skeleton(prim)
    raise RuntimeError("no UsdSkel Skeleton in the human USD")


class Rig:
    def __init__(self, skeleton):
        self.joints = list(skeleton.GetJointsAttr().Get())
        self.rest = list(skeleton.GetRestTransformsAttr().Get())
        self.parents = list(UsdSkel.Topology(self.joints).GetParentIndices())
        self.leaf = {j.split("/")[-1]: i for i, j in enumerate(self.joints)}
        self.rest_skel = self._concat(self.rest)
        self.contacts = [self.leaf[n] for n in CONTACT_JOINTS if n in self.leaf]

    def _concat(self, local):
        world = [None] * len(local)
        for i, parent in enumerate(self.parents):   # joints are ordered parent-first
            world[i] = Gf.Matrix4d(local[i]) * world[parent] if parent >= 0 else Gf.Matrix4d(local[i])
        return world

    def local_pose(self, rotations: dict) -> list:
        """Rest local transforms with the motion's skeleton-space rotations applied per joint."""
        local = list(self.rest)
        to_joint = {}
        for leaf, pairs in rotations.items():
            i = self.leaf.get(leaf)
            if i is None:
                continue
            inverse = to_joint.setdefault(i, self.rest_skel[i].GetInverse())
            rotation = Gf.Matrix4d(1.0)
            for axis, deg in pairs:
                local_axis = inverse.TransformDir(AXES[axis]).GetNormalized()
                rotation = rotation * Gf.Matrix4d(1.0).SetRotate(Gf.Rotation(local_axis, deg))
            local[i] = rotation * Gf.Matrix4d(self.rest[i])   # row vectors: rotate in the joint's frame
        return local

    def floor_offset(self, local) -> float:
        """How far the lowest contact joint moved up (+) / down (-) from the rest pose."""
        world = self._concat(local)
        rest = min(self.rest_skel[i].ExtractTranslation()[2] for i in self.contacts)
        return min(world[i].ExtractTranslation()[2] for i in self.contacts) - rest


def build_scene(human_usd: Path, out_path: Path, cfg: dict) -> Path:
    src = Usd.Stage.Open(str(human_usd))
    default = src.GetDefaultPrim()
    skel = _skeleton(src)
    rig = Rig(skel)
    human_id = default.GetName()
    rel_skel = skel.GetPrim().GetPath().MakeRelativePath(default.GetPath())

    if out_path.exists():
        out_path.unlink()
    stage = Usd.Stage.CreateNew(str(out_path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    fps = cfg["fps"]
    frames = int(math.ceil(motion.duration(cfg) * fps))
    stage.SetTimeCodesPerSecond(fps)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(frames)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    human = UsdGeom.Xform.Define(stage, f"/World/{human_id}")
    human.GetPrim().GetReferences().AddReference(os.path.relpath(human_usd, out_path.parent))
    translate = human.AddTranslateOp()
    rotate = human.AddRotateZOp()

    skel_path = human.GetPath().AppendPath(rel_skel)
    anim = UsdSkel.Animation.Define(stage, skel_path.GetParentPath().AppendChild("Anim"))
    UsdSkel.BindingAPI.Apply(stage.OverridePrim(skel_path)).CreateAnimationSourceRel().SetTargets([anim.GetPath()])
    anim.CreateJointsAttr(Vt.TokenArray(rig.joints))
    anim.CreateScalesAttr(Vt.Vec3hArray([Gf.Vec3h(1, 1, 1)] * len(rig.joints)))
    rest_translations = Vt.Vec3fArray([Gf.Vec3f(m.ExtractTranslation()) for m in rig.rest])
    anim.CreateTranslationsAttr(rest_translations)
    rotations_attr = anim.CreateRotationsAttr()

    position = Gf.Vec3d(0, 0, 0)
    for frame in range(frames + 1):
        t = frame / fps
        rotations, root = motion.pose_at(t, cfg)
        local = rig.local_pose(rotations)
        quats = [Gf.Quatf(Gf.Matrix4d(m).RemoveScaleShear().ExtractRotationQuat()) for m in local]
        rotations_attr.Set(Vt.QuatfArray(quats), frame)
        yaw = math.radians(root["yaw_deg"])
        position += Gf.Vec3d(math.sin(yaw), -math.cos(yaw), 0.0) * (root["forward_speed"] / fps)
        z = -rig.floor_offset(local) + root["lift_m"]
        translate.Set(Gf.Vec3d(position[0], position[1], z), frame)
        rotate.Set(root["yaw_deg"], frame)
    stage.GetRootLayer().Save()
    return out_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("human_usd")
    parser.add_argument("--out", help="output .usda (default: <id>_anim.usda next to the human)")
    parser.add_argument("--fps", type=int, default=motion.DEFAULTS["fps"])
    parser.add_argument("--walk-distance", type=float, default=motion.DEFAULTS["walk_distance_m"])
    parser.add_argument("--walk-speed", type=float, default=motion.DEFAULTS["walk_speed_mps"])
    parser.add_argument("--jump-height", type=float, default=motion.DEFAULTS["jump_height_m"])
    args = parser.parse_args(argv)
    human = Path(args.human_usd).resolve()
    out = Path(args.out).resolve() if args.out else human.with_name(f"{human.stem}_anim.usda")
    cfg = dict(motion.DEFAULTS, fps=args.fps, walk_distance_m=args.walk_distance,
               walk_speed_mps=args.walk_speed, jump_height_m=args.jump_height)
    build_scene(human, out, cfg)
    print(f"animated scene: {out} ({motion.duration(cfg):.1f} s at {cfg['fps']} fps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
