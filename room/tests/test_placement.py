import sys
from pathlib import Path

import pytest
from pxr import Gf, Usd, UsdGeom

from sdg_room.config import NULL, apply_overrides
from sdg_room.placement import FACING, Placement, entrance_outward
from sdg_room.sampling.manifest import build_room_spec
from sdg_room.usd.build import build_room_usd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "isaac"))


@pytest.mark.parametrize("facing", sorted(FACING))
def test_entrance_faces_the_configured_direction(cfg, facing):
    c = apply_overrides(cfg, {"export.placement.door_facing": facing, "variations.randomize_layout": True})
    walls = set()
    for i in range(12):
        spec = build_room_spec(c, i)
        walls.add(spec["layout"]["entrance"]["wall"])
        place = Placement(spec, c)
        d = place.dir_to_stage(entrance_outward(spec))
        assert d[0] == pytest.approx(FACING[facing][0], abs=1e-9) and d[1] == pytest.approx(FACING[facing][1], abs=1e-9)
        centre = place.to_stage([spec["footprint_m"][0] / 2, spec["footprint_m"][1] / 2, 0])
        assert centre[0] == pytest.approx(0, abs=1e-4) and centre[1] == pytest.approx(0, abs=1e-4)
    assert len(walls) >= 2, "test should cover west and long-wall entrances"


def test_root_transform_and_viewport_in_usd(cfg, tmp_path):
    spec = build_room_spec(cfg, 1)
    build = build_room_usd(cfg, spec, tmp_path / spec["id"], "test")
    stage = Usd.Stage.Open(build["usd"])
    root = stage.GetDefaultPrim()
    m = UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    door = spec["layout"]["entrance"]["center"]
    p = m.Transform(Gf.Vec3d(door[0], door[1], 0))
    assert p[1] < 0 and abs(p[1]) > abs(p[0]) - 1.5        # entrance on the -Y side, near the middle
    settings = stage.GetRootLayer().customLayerData["cameraSettings"]
    assert settings["boundCamera"] == "/OmniverseKit_Persp"
    assert settings["Perspective"]["position"][1] < p[1]   # viewport camera in front of the door


def test_room_corner_origin_keeps_old_frame(cfg):
    c = apply_overrides(cfg, {"export.placement.origin": "room_corner", "export.placement.door_facing": "-X"})
    spec = build_room_spec(c, 0)
    if spec["layout"]["entrance"]["wall"] == "west":
        place = Placement(spec, c)
        assert place.yaw_deg == 0 and place.translate == (0.0, 0.0, 0.0)


def test_compose_scene_still_puts_patient_on_marker(cfg, tmp_path):
    from compose_scene import compose
    spec = build_room_spec(cfg, 2)
    build = build_room_usd(cfg, spec, tmp_path / spec["id"], "test")
    human = tmp_path / "H.usda"
    s = Usd.Stage.CreateNew(str(human))
    s.SetDefaultPrim(UsdGeom.Xform.Define(s, "/H").GetPrim())
    s.GetRootLayer().Save()
    info = compose(build["usd"], tmp_path / "scene.usda", human, 1.3)
    want = Placement(spec, cfg).to_stage(spec["layout"]["marker"]["stand_point"] + [0.0])
    assert info["patient_stand"][0] == pytest.approx(want[0], abs=1e-3)
    assert info["patient_stand"][1] == pytest.approx(want[1], abs=1e-3)
    scene = Usd.Stage.Open(str(tmp_path / "scene.usda"))
    det = scene.GetPrimAtPath("/World/Room/Equipment/WallStand/Carriage")
    assert UsdGeom.Xformable(det).GetOrderedXformOps()[0].Get()[2] == pytest.approx(1.3)


@pytest.mark.parametrize("override,expected", [({"room.ceiling_height_m": 2.9, "room.ceiling_height_ft": NULL}, 2.9),
                                               ({"room.ceiling_height_ft": 9}, 2.743)])
def test_fixed_room_height(cfg, tmp_path, override, expected):
    c = apply_overrides(cfg, override)
    spec = build_room_spec(c, 0)
    assert spec["ceiling_height_m"] == pytest.approx(expected, abs=1e-3)
    build = build_room_usd(c, spec, tmp_path / spec["id"], "test")
    stage = Usd.Stage.Open(build["usd"])
    box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"]).ComputeUntransformedBound(
        stage.GetDefaultPrim()).ComputeAlignedRange()
    assert box.GetMax()[2] == pytest.approx(expected + 0.05, abs=2e-3)
