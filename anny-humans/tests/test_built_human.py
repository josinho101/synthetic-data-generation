"""End-to-end: one human built with Anny (slow: loads the model and builds ~1 minute)."""

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

pxr = pytest.importorskip("pxr")
from pxr import Usd, UsdGeom, UsdSkel  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def human(built_human):
    hid = built_human["spec"]["id"]
    meta = json.loads((built_human["dir"] / f"{hid}.json").read_text())
    stage = Usd.Stage.Open(str(built_human["dir"] / f"{hid}.usd"))
    return {**built_human, "id": hid, "meta": meta, "stage": stage}


def test_build_status(human):
    assert human["result"]["status"] in ("ok", "warn"), human["result"].get("error")
    assert human["result"]["validation"]["status"] in ("ok", "warn")
    assert (human["dir"] / f"{human['id']}.png").exists()
    assert not list(human["dir"].glob("*_anim.usda"))                 # animation is out of scope
    assert not list(human["dir"].glob("*_skeleton.png")) and not list(human["dir"].glob("*_landmarks.png"))


def test_isaac_skeleton_layout(human):
    stage = human["stage"]
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z and UsdGeom.GetStageMetersPerUnit(stage) == 1.0
    roots = [p for p in stage.Traverse() if p.IsA(UsdSkel.Root)]
    skels = [p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton)]
    assert len(roots) == 1 and len(skels) == 1
    joints = list(UsdSkel.Skeleton(skels[0]).GetJointsAttr().Get())
    names = [j.split("/")[-1] for j in joints]
    assert joints[0] == "SkelOrigin" and joints[1] == "SkelOrigin/root"
    assert len(joints) == 375 and sum(n.startswith("LM_") for n in names) == 175
    assert sum(n.startswith("AN_") for n in names) == 36
    retarget = yaml.safe_load((REPO / "sdg" / "configs" / "retarget_mpfb.yaml").read_text())
    missing = [j for j in retarget["tags"].values() if j not in names]
    assert not missing, f"retarget joints missing: {missing}"


def test_meshes_are_skinned_with_at_most_4_normalised_influences(human):
    for prim in human["stage"].Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        binding = UsdSkel.BindingAPI(prim)
        k = binding.GetJointIndicesPrimvar().GetElementSize()
        weights = np.asarray(binding.GetJointWeightsPrimvar().Get()).reshape(-1, k)
        assert k <= 4
        assert np.allclose(weights.sum(1), 1.0, atol=1e-4), prim.GetPath()


def test_body_mesh_and_materials(human):
    stage, hid = human["stage"], human["id"]
    body = stage.GetPrimAtPath(f"/{hid}/{hid}_rig/{hid}/base")
    assert body and body.IsA(UsdGeom.Mesh)
    assert len(UsdGeom.Mesh(body).GetPointsAttr().Get()) <= 13380
    from pxr import UsdShade
    material = UsdShade.MaterialBindingAPI(body).ComputeBoundMaterial()[0]
    assert material.GetSurfaceOutput().HasConnectedSource()
    assert material.GetSurfaceOutput("mdl").HasConnectedSource()     # OmniSurface for Isaac RTX


def test_metadata_for_sdg(human):
    meta, spec, cfg = human["meta"], human["spec"], human["cfg"]
    rng = cfg["population"]["age_range"]
    assert rng["min"] <= meta["identity"]["age_years"] <= rng["max"]
    assert abs(meta["body"]["height_cm"] - spec["target_height_cm"]) <= cfg["population"]["height_cm"]["tolerance_cm"]
    t7 = meta["landmarks"]["T7"]["rest_position_m"][2]
    assert meta["landmarks"]["xiphoid"]["rest_position_m"][2] < meta["landmarks"]["jugular_notch"]["rest_position_m"][2]
    assert 0.9 < t7 < 1.6
    asis = np.array(meta["landmarks"]["asis_L"]["rest_position_m"]) - np.array(meta["landmarks"]["asis_R"]["rest_position_m"])
    assert 0.18 < np.linalg.norm(asis) < 0.32
    assert meta["skeleton"]["rig"] == "anny_makehuman" and meta["anatomy"]["count"] > 60
    assert meta["clothing"]["items"] and all(i["asset"] for i in meta["clothing"]["items"])
