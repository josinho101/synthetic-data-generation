"""LandmarkReader on a tiny synthetic UsdSkel stage (no Blender needed)."""

from pxr import Gf, Usd, UsdSkel, Vt

from sdg_humans.isaac_landmarks import LandmarkReader


def test_reader_returns_world_positions(tmp_path):
    stage = Usd.Stage.CreateInMemory()
    UsdSkel.Root.Define(stage, "/H/rig")
    skel = UsdSkel.Skeleton.Define(stage, "/H/rig/skel")
    skel.CreateJointsAttr(Vt.TokenArray(["root", "root/LM_T7"]))
    rest = Vt.Matrix4dArray([Gf.Matrix4d(1.0), Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(0, 0.03, 1.25))])
    skel.CreateRestTransformsAttr(rest)
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray([Gf.Matrix4d(1.0), Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(0, 0.03, 1.25))]))
    reader = LandmarkReader(stage, "/H/rig/skel")
    assert reader.names == ["T7"]
    x, y, z = reader.world_positions()["T7"]
    assert abs(y - 0.03) < 1e-9 and abs(z - 1.25) < 1e-9
