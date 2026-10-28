"""Skeletal layer: registry, config validation, weight remapping and the USD rig rewrite (no Blender, no torch)."""

import copy

import numpy as np
import pytest

from sdg_humans.config.schema import validate
from sdg_humans.skeleton import LAYERS, get_layer
from sdg_humans.skeleton.zanatomy.weights import nearest_vertebra, remap


def test_registry_and_flags(cfg):
    for name in LAYERS:
        c = copy.deepcopy(cfg)
        c["skeleton"]["layer"] = name
        layer = get_layer(c)
        assert layer.name == name
    c["skeleton"]["layer"] = "zanatomy"
    za = get_layer(c)
    assert za.rig_replaced and za.needs_body_dump and not za.builds_in_blender
    c["skeleton"]["layer"] = "procedural"
    assert get_layer(c).builds_in_blender and not get_layer(c).rig_replaced


def test_skeleton_config_validation(cfg):
    c = copy.deepcopy(cfg)
    c["skeleton"]["layer"] = "bogus"
    assert any("skeleton.layer" in e for e in validate(c))
    c = copy.deepcopy(cfg)
    c["skeleton"]["zanatomy"]["length_bound"] = 2.0
    c["skeleton"]["zanatomy"]["contain_ramp"] = [150, 100]
    errs = validate(c)
    assert any("length_bound" in e for e in errs) and any("contain_ramp" in e for e in errs)
    assert not [e for e in validate(cfg) if e.startswith("skeleton")]


MAPS = {"weights": {"upperarm01_L": "humerus_L", "lowerarm01_L": "ulna_L", "root": "pelvis"},
        "weights_default": "skull", "spine_split": ["spine05", "spine04"],
        "spine_order": ["L5", "L4", "L3"]}


def _poly():
    return np.array([[0, 0, 1.0], [0, 0, 1.1], [0, 0, 1.2], [0, 0, 1.3]]), ["vertebra_L5", "vertebra_L4", "vertebra_L3"]


def test_spine_split_blends_two_vertebrae():
    shares = nearest_vertebra(np.array([0.0, 0.05, 1.10]), _poly())
    assert {b for b, _ in shares} == {"vertebra_L5", "vertebra_L4"}
    assert sum(s for _, s in shares) == pytest.approx(1.0)


def test_remap_normalised_and_drops_non_deforming():
    leafs = ["SkelOrigin", "upperarm01_L", "spine05", "LM_T1", "eye_L"]
    jidx = {"humerus_L": 1, "ulna_L": 2, "pelvis": 3, "skull": 4, "vertebra_L5": 5, "vertebra_L4": 6,
            "vertebra_L3": 7}
    I = np.array([[1, 2, 3, 0], [4, 1, 0, 0]])
    W = np.array([[0.5, 0.3, 0.1, 0.1], [0.6, 0.4, 0.0, 0.0]])
    P = np.array([[0.1, 0, 1.15], [0, 0, 1.6]])
    nI, nW, dropped = remap(I, W, leafs, P, MAPS, _poly(), jidx, 4)
    assert nI.shape == (2, 4) and np.allclose(nW.sum(1), 1.0)
    assert dropped == pytest.approx(0.2)                    # SkelOrigin + LM_T1 carry no weight
    assert 1 in nI[0] and (5 in nI[0] or 6 in nI[0])        # humerus + a vertebra from the spine split
    assert set(nI[1][nW[1] > 0]) == {4, 1}                  # eye -> skull (default), upperarm -> humerus


class _Ref:
    """A 4-bone anatomical rig + one bone mesh, enough for usd_rig.rewrite."""
    def __init__(self):
        self.names = ["pelvis", "vertebra_L5", "humerus_L", "ulna_L"]
        self.parent = np.array([-1, 0, 0, 2])
        f = np.repeat(np.eye(4)[None], 4, 0)
        f[0, :3, 3], f[1, :3, 3], f[2, :3, 3], f[3, :3, 3] = [0, 0, 1.0], [0, 0, 1.05], [0.2, 0, 1.4], [0.3, 0, 1.1]
        self.frames = f
        self.maps = dict(MAPS, spine_order=["L5"])
        self.mesh_keys = ["bone_humerus_L"]
        self.version = "test"

    def mesh(self, key):
        return np.array([[0.2, 0, 1.4], [0.21, 0, 1.2], [0.2, 0.01, 1.3]]), np.array([[0, 1, 2]]), "humerus_L"


def _stage(path):
    from pxr import Gf, Usd, UsdGeom, UsdSkel, Vt
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdSkel.Root.Define(stage, "/H/H_rig")
    skel = UsdSkel.Skeleton.Define(stage, "/H/H_rig/H_rig")
    joints = ["SkelOrigin", "SkelOrigin/root", "SkelOrigin/root/upperarm01_L", "SkelOrigin/root/upperarm01_L/LM_elbow"]
    skel.CreateJointsAttr(Vt.TokenArray(joints))
    binds = [Gf.Matrix4d(1.0)] * 3 + [Gf.Matrix4d(1.0).SetTranslate(Gf.Vec3d(0.3, 0, 1.1))]
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray(binds))
    skel.CreateRestTransformsAttr(Vt.Matrix4dArray(binds))
    m = UsdGeom.Mesh.Define(stage, "/H/H_rig/H/base")
    m.CreatePointsAttr([Gf.Vec3f(0.2, 0, 1.3), Gf.Vec3f(0, 0, 1.0), Gf.Vec3f(0.1, 0, 1.2)])
    m.CreateFaceVertexCountsAttr([3])
    m.CreateFaceVertexIndicesAttr([0, 1, 2])
    b = UsdSkel.BindingAPI.Apply(m.GetPrim())
    b.CreateSkeletonRel().SetTargets([skel.GetPrim().GetPath()])
    b.CreateJointsAttr(Vt.TokenArray(joints))
    b.CreateJointIndicesPrimvar(False, 2).Set(Vt.IntArray([2, 1, 1, 0, 2, 1]))
    b.CreateJointWeightsPrimvar(False, 2).Set(Vt.FloatArray([0.8, 0.2, 1.0, 0.0, 0.5, 0.5]))
    old = UsdGeom.Mesh.Define(stage, "/H/H_rig/bone_old/bone_old")          # an old procedural bone mesh
    old.CreatePointsAttr([Gf.Vec3f(0, 0, 1)])
    stage.SetDefaultPrim(stage.GetPrimAtPath("/H"))
    stage.GetRootLayer().Save()
    return root


def test_usd_rig_rewrite(tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdSkel

    from sdg_humans.skeleton.zanatomy.usd_rig import rewrite
    from sdg_humans.usd_post import add_root_joint, set_anatomy_purpose

    path = tmp_path / "H.usda"
    _stage(path)
    ref = _Ref()
    fit = {"W": ref.frames.copy(), "S": np.ones((4, 3))}
    out = rewrite(path, ref, fit, {}, ("LM_", "AN_"))
    stage = Usd.Stage.Open(str(path))
    skel = UsdSkel.Skeleton(stage.GetPrimAtPath("/H/H_rig/H_rig"))
    joints = [str(j) for j in skel.GetJointsAttr().Get()]
    assert joints == ["SkelOrigin", "SkelOrigin/pelvis", "SkelOrigin/pelvis/vertebra_L5", "SkelOrigin/pelvis/humerus_L",
                      "SkelOrigin/pelvis/humerus_L/ulna_L"]          # Z-Anatomy only, landmark joint dropped
    assert out["joint_paths"] == {"SkelOrigin/root/upperarm01_L/LM_elbow": None}
    b = UsdSkel.BindingAPI(stage.GetPrimAtPath("/H/H_rig/H/base"))
    W = np.array(b.GetJointWeightsPrimvar().Get()).reshape(-1, 4)
    I = np.array(b.GetJointIndicesPrimvar().Get()).reshape(-1, 4)
    assert np.allclose(W.sum(1), 1.0) and I[0][0] == 3                # upperarm01_L -> humerus_L (index 3)
    assert not stage.GetPrimAtPath("/H/H_rig/bone_old")
    bone = stage.GetPrimAtPath("/H/H_rig/ZAnatomy/bone_humerus_L")
    assert bone and UsdSkel.BindingAPI(bone).GetJointsAttr().Get()[0] == "SkelOrigin/pelvis/humerus_L"
    assert set_anatomy_purpose(stage, "guide") >= 1
    assert add_root_joint(stage, "SkelOrigin") is False              # already rooted: idempotent
    assert UsdGeom.Imageable(bone).ComputePurpose() == UsdGeom.Tokens.guide


def test_usd_rig_keeps_landmark_joints_when_asked(tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdSkel

    from sdg_humans.skeleton.zanatomy.usd_rig import rewrite
    path = tmp_path / "H.usda"
    _stage(path)
    ref = _Ref()
    out = rewrite(path, ref, {"W": ref.frames.copy(), "S": np.ones((4, 3))}, {"keep_landmark_joints": True})
    new = out["joint_paths"]["SkelOrigin/root/upperarm01_L/LM_elbow"]
    assert new == "SkelOrigin/pelvis/humerus_L/LM_elbow"
    stage = Usd.Stage.Open(str(path))
    skel = UsdSkel.Skeleton(stage.GetPrimAtPath("/H/H_rig/H_rig"))
    joints = [str(j) for j in skel.GetJointsAttr().Get()]
    bind = np.array(skel.GetBindTransformsAttr().Get()[joints.index(new)]).T
    assert np.allclose(bind[:3, 3], [0.3, 0, 1.1])                    # world bind unchanged
