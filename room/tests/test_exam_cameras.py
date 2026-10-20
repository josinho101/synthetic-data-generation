"""RGB-D exam cameras (Intel RealSense D455): tripods beside the patient, source camera, top camera."""

import math

import numpy as np
import pytest
from pxr import Gf, Usd, UsdGeom

from sdg_room.config import apply_overrides
from sdg_room.layout.geometry import Rect
from sdg_room.layout.solver import detector_axes
from sdg_room.pipeline.validate import validate_usd
from sdg_room.sampling.manifest import build_room_spec
from sdg_room.usd.build import build_room_usd

EXAM = ("RealSense_D455_Left", "RealSense_D455_Right", "RealSense_D455_Front", "RealSense_D455_Top")


@pytest.fixture(scope="module")
def specs(cfg):
    return [build_room_spec(cfg, i) for i in range(20)]


def _cams(spec):
    return {c["name"]: c for c in spec["cameras"] if c.get("rig")}


def _view(cam):
    v = np.array(cam["target"]) - np.array(cam["position"])
    return v / np.linalg.norm(v)


def test_all_exam_cameras_present(specs):
    for s in specs:
        cams = _cams(s)
        assert set(cams) == set(EXAM), s["id"]
        for c in cams.values():
            assert c["rig"] == "d455" and set(c["streams"]) == {"color", "depth"}


def test_lateral_tripods_at_radius_and_height(specs):
    for s in specs:
        eq = s["layout"]["equipment"]
        cx, cy = eq["detector"]["center"][:2]
        n, left = detector_axes(eq)
        room = Rect(0, 0, *s["footprint_m"])
        block = Rect.from_list(s["layout"]["changing_room"]["block"])
        cams = _cams(s)
        for name, sign in (("RealSense_D455_Left", 1), ("RealSense_D455_Right", -1)):
            c = cams[name]
            x, y, z = c["position"]
            assert math.hypot(x - cx, y - cy) == pytest.approx(1.4, abs=2e-3), (s["id"], name)
            assert z == pytest.approx(1.0, abs=1e-6)
            assert ((x - cx) * left[0] + (y - cy) * left[1]) * sign > 0, (s["id"], name)   # on its own side
            assert (x - cx) * n[0] + (y - cy) * n[1] >= -1e-6                               # in front of the wall
            stand = Rect.from_list(s["layout"]["exam_cameras"][name]["stand_rect"])
            assert stand.inside(room) and not stand.overlaps(block)
            others = [Rect.from_list(r) for k, r in s["layout"]["obstacles"].items() if k != f"camera_stand_{name}"]
            assert not any(stand.overlaps(o) for o in others), (s["id"], name)
            assert c["movement_coverage"]["body"] >= 0.85, (s["id"], name, c["movement_coverage"])


def test_front_left_right_portrait_upright_top_landscape(specs):
    """Front / Left / Right: upright camera with a tall image (portrait optics); Top: landscape, looking down."""
    for s in specs:
        cams = _cams(s)
        for name in ("RealSense_D455_Front", "RealSense_D455_Left", "RealSense_D455_Right"):
            c = cams[name]
            assert c["orientation"] == "portrait" and c["up"][2] > 0.99, name   # upright, not rolled
            assert (c["fov_h_deg"], c["fov_v_deg"], c["resolution"]) == (58.0, 87.0, [720, 1280])
            assert (c["streams"]["color"]["fov_h_deg"], c["streams"]["color"]["resolution"]) == (65.0, [800, 1280])
        for name in ("RealSense_D455_Left", "RealSense_D455_Right"):
            assert abs(_view(cams[name])[2]) < 0.2          # looks across at the patient, not down
        top = cams["RealSense_D455_Top"]
        assert top["orientation"] == "landscape" and top["resolution"] == [1280, 720] and _view(top)[2] < -0.9


def test_every_exam_camera_focused_on_the_patient(specs):
    """Each camera aims at the patient standing on the floor marker and its focus distance is the distance to him."""
    for s in specs:
        sx, sy = s["layout"]["marker"]["stand_point"]
        for c in _cams(s).values():
            tx, ty, _ = c["target"]
            assert math.hypot(tx - sx, ty - sy) < 0.3, (s["id"], c["name"])
            eye = np.array(c["position"])
            assert c["focus_distance_m"] == pytest.approx(float(np.linalg.norm(np.array(c["target"]) - eye)), abs=1e-3)
            assert c["movement_coverage"]["body" if c["name"] != "RealSense_D455_Top" else "floor"] >= 0.85


def test_source_camera_on_tube_facing_patient(specs):
    for s in specs:
        eq = s["layout"]["equipment"]
        c = _cams(s)["RealSense_D455_Front"]
        assert np.linalg.norm(np.array(c["position"]) - np.array(eq["focal_spot"])) < 0.3
        beam = np.array(eq["beam_axis"], float)
        assert _view(c) @ beam > 0.7          # along the beam, tilted down to the patient centre
        assert c["movement_coverage"]["body"] >= 0.9, (s["id"], c["movement_coverage"])


def test_top_camera_extends_from_detector_and_looks_down(cfg, specs):
    hh = cfg["equipment"]["detector"]["housing_size_m"][1]
    for s in specs:
        eq = s["layout"]["equipment"]
        cx, cy, h = eq["detector"]["center"]
        n, _ = detector_axes(eq)
        c = _cams(s)["RealSense_D455_Top"]
        x, y, z = c["position"]
        assert (x - cx) * n[0] + (y - cy) * n[1] == pytest.approx(0.2, abs=1e-6)
        assert z == pytest.approx(h + hh / 2 + 0.1, abs=1e-6)
        assert _view(c)[2] < -0.9
        assert c["movement_coverage"]["floor"] == 1.0
        assert c["attached_to"] == "wall_stand_carriage"


def test_min_depth_reported_for_top_camera(specs):
    """The top camera sits at detector-top height: a tall patient's head comes closer than the D455 minimum depth.
    Reported as a note + camera fields (expected), not as a room warning."""
    for s in specs:
        top = _cams(s)["RealSense_D455_Top"]
        assert not top["within_depth_range"] and top["min_patient_distance_m"] < 0.6
        assert any("RealSense_D455_Top" in n and "minimum depth" in n for n in s["layout"]["notes"])
        assert not any("minimum depth" in w for w in s["layout"]["warnings"])
        assert _cams(s)["RealSense_D455_Left"]["within_depth_range"]


def test_exam_cameras_configurable(cfg):
    c = apply_overrides(cfg, {"cameras.exam_cameras.cameras.RealSense_D455_Left.radius_m": 1.2,
                              "cameras.exam_cameras.cameras.RealSense_D455_Left.height_m": [0.9, 1.1],
                              "cameras.exam_cameras.cameras.RealSense_D455_Right.orientation": "landscape",
                              "cameras.exam_cameras.cameras.RealSense_D455_Top.extension_m": 0.3,
                              "cameras.exam_cameras.cameras.RealSense_D455_Front.enabled": False,
                              "cameras.exam_cameras.defaults.streams": ["depth"]})
    s = build_room_spec(c, 0)
    cams = _cams(s)
    eq = s["layout"]["equipment"]
    cx, cy = eq["detector"]["center"][:2]
    n, _ = detector_axes(eq)
    assert "RealSense_D455_Front" not in cams
    left = cams["RealSense_D455_Left"]
    assert math.hypot(left["position"][0] - cx, left["position"][1] - cy) == pytest.approx(1.2, abs=2e-3)
    assert 0.9 <= left["position"][2] <= 1.1
    assert cams["RealSense_D455_Right"]["orientation"] == "landscape" and cams["RealSense_D455_Right"]["fov_h_deg"] == 87.0
    top = cams["RealSense_D455_Top"]["position"]
    assert (top[0] - cx) * n[0] + (top[1] - cy) * n[1] == pytest.approx(0.3, abs=1e-6)
    assert all(set(x["streams"]) == {"depth"} for x in cams.values())
    assert not _cams(build_room_spec(apply_overrides(cfg, {"cameras.exam_cameras.enabled": False}), 0))


def test_bad_exam_camera_config_rejected(cfg):
    from sdg_room.config.schema import validate
    bad = {"cameras.exam_cameras.cameras.RealSense_D455_Left.mount": "ceiling",
           "cameras.exam_cameras.cameras.RealSense_D455_Right.radius_m": -1,
           "cameras.exam_cameras.cameras.RealSense_D455_Top.orientation": "sideways",
           "cameras.exam_cameras.cameras.RealSense_D455_Front.rig": "kinect"}
    errors = validate(apply_overrides(cfg, bad))
    for key in ("RealSense_D455_Left.mount", "RealSense_D455_Right.radius_m", "RealSense_D455_Top.orientation", "RealSense_D455_Front.rig"):
        assert any(key in e for e in errors), key


def test_exam_cameras_in_usd(cfg, tmp_path, specs):
    spec = specs[0]
    build = build_room_usd(cfg, spec, tmp_path / spec["id"], "test")
    assert validate_usd(build["usd"], spec["footprint_m"], cameras=spec["cameras"])["status"] == "ok"
    stage = Usd.Stage.Open(build["usd"])
    landscape = {"RGB": (90.0, 65.0), "Depth": (87.0, 58.0)}
    cams = _cams(spec)
    for name in EXAM:
        rig = stage.GetPrimAtPath(f"/Room/Cameras/{name}")
        assert rig and rig.GetAttribute("sdg:rig").Get() == "d455"
        assert stage.GetPrimAtPath(f"/Room/Cameras/{name}_Mount/Head/Body")
        portrait = cams[name]["orientation"] == "portrait"
        for suffix, fov in landscape.items():
            fh, fv = fov[::-1] if portrait else fov
            # unique stream prim names, so Isaac's camera menu shows e.g. RealSense_D455_Left_RGB
            cam = UsdGeom.Camera(stage.GetPrimAtPath(f"/Room/Cameras/{name}/{name}_{suffix}"))
            f = cam.GetFocalLengthAttr().Get()
            assert math.degrees(2 * math.atan(cam.GetHorizontalApertureAttr().Get() / (2 * f))) == pytest.approx(fh, abs=0.5)
            assert math.degrees(2 * math.atan(cam.GetVerticalApertureAttr().Get() / (2 * f))) == pytest.approx(fv, abs=0.5)
            assert cam.GetFocusDistanceAttr().Get() == pytest.approx(cams[name]["focus_distance_m"], abs=1e-3)
            assert cam.GetFStopAttr().Get() == 0.0
    # the colour stream sits beside the depth origin (left imager) on the same rig
    m_c = UsdGeom.Xformable(stage.GetPrimAtPath("/Room/Cameras/RealSense_D455_Top/RealSense_D455_Top_RGB")).ComputeLocalToWorldTransform(0)
    m_d = UsdGeom.Xformable(stage.GetPrimAtPath("/Room/Cameras/RealSense_D455_Top/RealSense_D455_Top_Depth")).ComputeLocalToWorldTransform(0)
    assert (m_c.ExtractTranslation() - m_d.ExtractTranslation()).GetLength() == pytest.approx(0.059, abs=1e-4)
    assert Gf.Dot(m_c.TransformDir(Gf.Vec3d(0, 0, -1)), m_d.TransformDir(Gf.Vec3d(0, 0, -1))) > 0.999
    assert stage.GetPrimAtPath("/Room/Cameras/RealSense_D455_Left_Mount/Leg0")
