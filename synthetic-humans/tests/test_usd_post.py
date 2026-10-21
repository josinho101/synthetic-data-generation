"""usd_post: clothing hole faces (with an opening), anatomy purpose, identity root joint (usd-core)."""

import pytest

pxr = pytest.importorskip("pxr")
from pxr import Gf, Usd, UsdGeom, UsdSkel  # noqa: E402

from sdg_humans import usd_post  # noqa: E402


def _grid(stage, path, z, x0, x1, n=10, gap=None):
    """Mesh grid in the plane z (normals +z after triangulation order), optional gap (x range) left out."""
    mesh = UsdGeom.Mesh.Define(stage, path)
    pts, counts, idx = [], [], []
    xs = [x0 + (x1 - x0) * i / n for i in range(n + 1)]
    for j in range(2):
        for x in xs:
            pts.append(Gf.Vec3f(x, 0.2 * j, z))
    for i in range(n):
        if gap and gap[0] <= (xs[i] + xs[i + 1]) / 2 <= gap[1]:
            continue
        a, b = i, i + 1
        idx += [a, b, b + n + 1, a + n + 1]
        counts.append(4)
    mesh.CreatePointsAttr(pts)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(idx)
    return mesh


def test_clothing_holes_keep_openings():
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/H/H_rig")
    _grid(stage, "/H/H_rig/H/base", 0.0, 0.0, 1.0, n=20)                       # skin
    _grid(stage, "/H/H_rig/H_shirt/shirt", 0.02, 0.0, 0.6, n=12, gap=(0.25, 0.35))   # cloth with a slit
    info = usd_post.clothing_hole_faces(stage, ["shirt"], 0.07, 0.75)
    holes = set(UsdGeom.Mesh(stage.GetPrimAtPath("/H/H_rig/H/base")).GetHoleIndicesAttr().Get())
    assert info["hole_faces"] == len(holes) > 0
    centre_x = {f: (f + 0.5) / 20 for f in range(20)}
    assert all(centre_x[f] < 0.6 for f in holes)                               # nothing hidden beyond the cloth
    assert not any(0.27 < centre_x[f] < 0.33 for f in holes)                   # skin under the slit stays visible


def test_root_joint_and_anatomy_purpose():
    stage = Usd.Stage.CreateInMemory()
    root = UsdSkel.Root.Define(stage, "/H/H_rig")
    skel = UsdSkel.Skeleton.Define(stage, "/H/H_rig/H_rig")
    skel.CreateJointsAttr(["root", "root/spine"])
    m = Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(0, 0, 0.9))
    skel.CreateRestTransformsAttr([m, Gf.Matrix4d(1.0)])
    skel.CreateBindTransformsAttr([m, m])
    body = _grid(stage, "/H/H_rig/H/base", 0.0, 0.0, 1.0, n=2)
    UsdSkel.BindingAPI.Apply(body.GetPrim())
    UsdGeom.Xform.Define(stage, "/H/H_rig/bone_femur_L")
    bone = UsdGeom.Mesh.Define(stage, "/H/H_rig/bone_femur_L/bone_femur_L")
    assert usd_post.add_root_joint(stage, "SkelOrigin")
    assert list(skel.GetJointsAttr().Get()) == ["SkelOrigin", "SkelOrigin/root", "SkelOrigin/root/spine"]
    assert len(skel.GetRestTransformsAttr().Get()) == 3
    assert list(UsdSkel.BindingAPI(body.GetPrim()).GetJointsAttr().Get())[0] == "SkelOrigin/root"
    assert not usd_post.add_root_joint(stage, "SkelOrigin")                    # idempotent
    with pytest.raises(ValueError):
        usd_post.add_root_joint(stage, "Root")
    assert usd_post.set_anatomy_purpose(stage, "guide") == 2                   # bone_femur_L Xform + mesh
    assert UsdGeom.Imageable(bone).GetPurposeAttr().Get() == "guide"
    assert root
