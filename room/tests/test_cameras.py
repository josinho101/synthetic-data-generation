import pytest
from pxr import Gf, Usd, UsdGeom

from sdg_room.config import apply_overrides
from sdg_room.layout.geometry import Rect
from sdg_room.pipeline.validate import validate_usd
from sdg_room.sampling.manifest import build_room_spec
from sdg_room.usd.build import build_room_usd


@pytest.fixture(scope="module")
def specs(cfg):
    return [build_room_spec(cfg, i) for i in range(20)]


def test_default_cameras_present(specs):
    for s in specs:
        assert {c["name"] for c in s["cameras"]} == {"CeilingCam_FarLeft", "CeilingCam_FarRight", "CeilingCam_CheckIn", "Viewer_Entrance",
                                                     "RealSense_D455_Left", "RealSense_D455_Right", "RealSense_D455_Front", "RealSense_D455_Top"}


def test_far_cameras_high_on_the_wall_opposite_the_entrance(specs):
    """Opposite the X-ray room's entry: the connecting door from the check-in room in the west wall."""
    for s in specs:
        out = (-1.0, 0.0)
        door = s["layout"]["changing_room"]["door"]["center"]
        H = s["ceiling_height_m"]
        cams = {c["name"]: c for c in s["cameras"]}
        room = Rect(0, 0, *s["footprint_m"])
        for name in ("CeilingCam_FarLeft", "CeilingCam_FarRight"):
            p = cams[name]["position"]
            assert room.contains(p[0], p[1]) and H - 0.35 < p[2] < H
            # far from the entrance along the inward direction
            assert (p[0] - door[0]) * -out[0] + (p[1] - door[1]) * -out[1] > 1.5
        # left is on the viewer's left when looking into the room
        inward = (-out[0], -out[1])
        left = (-inward[1], inward[0])
        l, r = cams["CeilingCam_FarLeft"]["position"], cams["CeilingCam_FarRight"]["position"]
        assert l[0] * left[0] + l[1] * left[1] > r[0] * left[0] + r[1] * left[1]


def test_checkin_camera_inside_changing_room(specs):
    for s in specs:
        cam = next(c for c in s["cameras"] if c["name"] == "CeilingCam_CheckIn")
        assert cam["position"][0] < 0                    # the check-in room is outside the X-ray room
        assert Rect.from_list(s["layout"]["changing_room"]["interior"]).contains(*cam["position"][:2])


def test_cameras_in_usd_look_at_targets(cfg, tmp_path, specs):
    spec = specs[0]
    build = build_room_usd(cfg, spec, tmp_path / spec["id"], "test")
    assert validate_usd(build["usd"], spec["footprint_m"], cameras=spec["cameras"])["status"] == "ok"
    stage = Usd.Stage.Open(build["usd"])
    for cam in (c for c in spec["cameras"] if not c.get("rig")):     # RGB-D rigs: tests/test_exam_cameras.py
        prim = stage.GetPrimAtPath(f"/Room/Cameras/{cam['name']}")
        assert prim.IsA(UsdGeom.Camera)
        assert UsdGeom.Camera(prim).GetFocalLengthAttr().Get() == pytest.approx(cam["focal_length_mm"])
        assert tuple(prim.GetAttribute("sdg:resolution").Get()) == tuple(cam["resolution"])


def test_camera_can_be_disabled_and_reconfigured(cfg):
    c = apply_overrides(cfg, {"cameras.cameras.CeilingCam_CheckIn.enabled": False,
                              "cameras.cameras.CeilingCam_FarLeft.auto_frame": False,
                              "cameras.cameras.CeilingCam_FarLeft.target": "floor_marker",
                              "cameras.cameras.CeilingCam_FarLeft.resolution": [640, 480]})
    s = build_room_spec(c, 0)
    names = {cam["name"]: cam for cam in s["cameras"]}
    assert "CeilingCam_CheckIn" not in names
    assert names["CeilingCam_FarLeft"]["target_name"] == "floor_marker" and names["CeilingCam_FarLeft"]["resolution"] == [640, 480]
    assert not build_room_spec(apply_overrides(cfg, {"cameras.enabled": False}), 0)["cameras"]


def test_camera_streams_do_not_change_room_choices(cfg):
    a = build_room_spec(cfg, 3)
    b = build_room_spec(apply_overrides(cfg, {"cameras.defaults.position_jitter_m": 0.0}), 3)
    assert a["layout"] == b["layout"] and a["lux_target"] == b["lux_target"]


def test_bad_camera_config_rejected(cfg):
    from sdg_room.config.schema import validate
    errors = validate(apply_overrides(cfg, {"cameras.cameras.CeilingCam_FarLeft.mount": "ceiling_fan"}))
    assert any("mount" in e for e in errors)




def test_room_cameras_see_every_patient_action(specs):
    """Union of the two X-ray-room cameras: patient on the marker fully, the walking body >= 95 %, table / stretcher."""
    for s in specs:
        cov = s["camera_coverage"]
        assert cov["marker"] == 1.0, s["id"]
        assert cov["walk_path"] >= 0.95, (s["id"], cov)
        assert cov.get("support", 1.0) >= 0.9, (s["id"], cov)


def test_auto_framed_cameras_use_wide_lens_within_limits(cfg, specs):
    lo, hi = cfg["cameras"]["coverage"]["focal_length_mm"]
    for s in specs:
        for cam in s["cameras"]:
            if cam["auto_frame"]:
                assert lo - 1e-6 <= cam["focal_length_mm"] <= hi + 1e-6
                assert cam["coverage"]["marker"] == 1.0 or s["camera_coverage"]["marker"] == 1.0


def test_occlusion_slab_test():
    import numpy as np
    from sdg_room.layout.coverage import unoccluded
    eye = np.array([0.0, 0.0, 2.0])
    pts = np.array([[4.0, 0.0, 0.0], [0.0, 4.0, 0.0]])
    box = np.array([[1.8, -0.2, 0.0, 2.2, 0.2, 2.0]])        # wall-like box on the first ray only
    assert unoccluded(eye, pts, box).tolist() == [False, True]


def test_manual_framing_still_possible(cfg):
    c = apply_overrides(cfg, {"cameras.cameras.CeilingCam_FarLeft.auto_frame": False,
                              "cameras.cameras.CeilingCam_FarLeft.focal_length_mm": 12.0})
    cam = next(x for x in build_room_spec(c, 0)["cameras"] if x["name"] == "CeilingCam_FarLeft")
    assert not cam["auto_frame"] and cam["focal_length_mm"] == 12.0 and "coverage" in cam
