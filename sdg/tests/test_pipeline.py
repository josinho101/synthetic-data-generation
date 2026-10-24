"""Pure-Python tests (no Isaac Sim): config, input discovery, visit plan, arm targets, SD numbering, timeline."""

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sdg_xray import sd as sdmod  # noqa: E402
from sdg_xray.config import ConfigError, load_config  # noqa: E402
from sdg_xray.paths import CONFIG_DIR, DEFAULT_HUMANS_ROOT, DEFAULT_ROOMS_ROOT, REPO_ROOT  # noqa: E402
from sdg_xray.sources import resolve_run, select_items  # noqa: E402
from sdg_xray.visit import plan_visit, projection_facing, room_anchors  # noqa: E402

HUMAN_JSON = {
    "id": "H9999",
    "landmarks": {name: {"rest_position_m": pos} for name, pos in {
        "vertex": [0.0, -0.077, 1.635], "iliac_crest_L": [0.116, 0.013, 1.009], "iliac_crest_R": [-0.116, 0.013, 1.009],
        "T7": [0.0, 0.0, 1.25]}.items()},
}
ROOM_JSON = {
    "id": "R9999",
    "placement": {"yaw_deg": 90.0},
    "entrance": {"out_normal": [-1, 0]},
    "anchors": {"stage": {
        "detector_normal": [1.0, 0.0, 0.0], "entrance_door": [1.6, -4.5, 0.0], "entrance_yaw_deg": -180.0,
        "patient_route": [{"step": s, "position": p} for s, p in (
            ("entrance", [1.6, -4.15, 0]), ("check_in", [1.59, -3.57, 0]), ("connecting_door", [1.59, -3.05, 0]),
            ("entrance_stand", [1.59, -2.5, 0]), ("patient_stand", [-1.58, 1.41, 0]))],
    }},
}


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG_DIR)


def _make_run(root: Path, kind: str, ids, status="ok", name="run-20260101-000000"):
    run = root / name
    for i in ids:
        folder = run / kind / i
        folder.mkdir(parents=True)
        (folder / f"{i}.usd").write_text("")
        (folder / f"{i}.json").write_text("{}")
    (run / "results.json").write_text(json.dumps({i: {"status": status} for i in ids}))
    return run


def test_default_config_valid(cfg):
    assert cfg["run"]["humans"]["count"] == 2 and cfg["run"]["rooms"]["count"] == 1
    assert cfg["run"]["exams"]["CHEST"] == ["PA", "LLAT", "RLAT"]


def test_unknown_projection_rejected():
    with pytest.raises(ConfigError, match="not defined"):
        load_config(CONFIG_DIR, {"run.exams": {"CHEST": ["PA", "XLAT"]}})


def test_latest_run_and_selection(tmp_path):
    _make_run(tmp_path, "humans", ["H0001", "H0002"], name="run-20260101-000000")
    newest = _make_run(tmp_path, "humans", ["H0001", "H0002", "H0003"], name="run-20260102-000000")
    _make_run(tmp_path, "humans", ["H0001"], status="failed", name="run-20260103-000000")   # nothing ok -> skipped
    run = resolve_run(tmp_path, "humans", tmp_path)
    assert run == newest
    assert [h["id"] for h in select_items(run, "humans", count=2)] == ["H0001", "H0002"]
    assert [h["id"] for h in select_items(run, "humans", ids=["H0003"])] == ["H0003"]
    with pytest.raises(ConfigError, match="only 3"):
        select_items(run, "humans", count=5)
    with pytest.raises(ConfigError, match="H0009"):
        select_items(run, "humans", ids=["H0009"])


def test_run_dir_given_directly(tmp_path):
    run = _make_run(tmp_path, "rooms", ["R0001"])
    assert resolve_run(run, "rooms", tmp_path) == run
    with pytest.raises(ConfigError):
        resolve_run(tmp_path / "missing", "rooms", tmp_path)


def test_room_anchors_and_facings():
    a = room_anchors(ROOM_JSON)
    assert a["entrance_out"][:2] == pytest.approx([0.0, -1.0])           # door faces -Y on the stage
    assert a["face_detector"][:2] == pytest.approx([-1.0, 0.0])          # detector normal points at the patient
    assert a["entrance_facing"][:2] == pytest.approx([0.0, 1.0])         # into the room
    d = a["face_detector"]
    left, right = projection_facing(d, "left"), projection_facing(d, "right")
    # RLAT (turn left): the patient's right side (facing rotated -90 deg) points at the detector (= d)
    right_side_after_left_turn = [left[1], -left[0]]
    assert right_side_after_left_turn == pytest.approx(d[:2])
    left_side_after_right_turn = [-right[1], right[0]]
    assert left_side_after_right_turn == pytest.approx(d[:2])


def test_plan_visit_order(cfg):
    steps = plan_visit(ROOM_JSON, ["PA", "LLAT", "RLAT"], cfg)
    walks = [s["target"] for s in steps if s["op"] == "walk"]
    assert walks == ["check_in", "entrance_stand", "patient_stand", "entrance_stand", "outside"]
    assert steps[0]["op"] == "spawn" and steps[0]["position"][:2] == pytest.approx([1.6, -6.0])
    assert steps[-2]["waypoints"][-1] == steps[0]["position"]           # leaves back to the start point outside
    fov = [(s["projection"], s["on"]) for s in steps if s["op"] == "fov"]
    assert fov == [("PA", True), ("PA", False), ("LLAT", True), ("LLAT", False), ("RLAT", True), ("RLAT", False)]
    for k, s in enumerate(steps):                                        # light is on exactly fov_on_s
        if s["op"] == "fov" and s["on"]:
            assert steps[k + 1]["op"] == "idle" and steps[k + 1]["duration"] == cfg["poses"]["timing"]["fov_on_s"]
            assert steps[k + 2]["op"] == "fov" and not steps[k + 2]["on"]
    arms = [(s["projection"], s["pose"]) for s in steps if s["op"] == "arms"]
    assert arms == [("PA", "hands_on_hip"), ("PA", "down"), ("LLAT", "hands_on_head"), ("LLAT", "down"),
                    ("RLAT", "hands_on_head"), ("RLAT", "down")]
    assert [s["index"] for s in steps] == list(range(1, len(steps) + 1))


def test_room_without_route_rejected(cfg):
    broken = json.loads(json.dumps(ROOM_JSON))
    broken["anchors"]["stage"]["patient_route"] = broken["anchors"]["stage"]["patient_route"][:3]
    with pytest.raises(ConfigError, match="entrance_stand"):
        plan_visit(broken, ["PA"], cfg)


def _library_like_skeleton():
    """Minimal skeleton with the motion library's joint names and T-pose-ish idle proportions (Y up, +Z front, cm)."""
    from pxr import Gf
    spec = [  # name, parent, local translation (cm)
        ("Root", None, (0, 0, 0)), ("Pelvis", "Root", (0, 95, 0)), ("Chest", "Pelvis", (0, 30, 0)),
        ("Head", "Chest", (0, 40, 0))]
    for side, sx, n in (("L", 1, "L"), ("R", -1, "R")):
        spec += [(f"{n}_Clavicle", "Chest", (sx * 3, 20, 3)), (f"{n}_UpArm", f"{n}_Clavicle", (sx * 16, -2, -5)),
                 (f"{n}_LoArm", f"{n}_UpArm", (sx * 1, -26, -2)), (f"{n}_Wrist", f"{n}_LoArm", (sx * 1, -24, 4)),
                 (f"{n}_MiddleFinger1", f"{n}_Wrist", (0, -2, 1)), (f"{n}_IndexFinger1", f"{n}_Wrist", (0, -2, 3)),
                 (f"{n}_PinkyFinger1", f"{n}_Wrist", (0, -2, -2))]
    paths = {}
    for name, parent, _ in spec:
        paths[name] = name if parent is None else f"{paths[parent]}/{name}"
    joints = [paths[name] for name, _, _ in spec]
    frame = ([Gf.Quatf(1, 0, 0, 0)] * len(spec), [Gf.Vec3f(*t) for _, _, t in spec])
    return joints, [frame, frame]


def test_pose_clip_ik_and_annotations(cfg, tmp_path):
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdSkel
    from sdg_xray import pose_clips
    joints, frames = _library_like_skeleton()
    for name, pose in cfg["poses"]["arm_poses"].items():
        info = pose_clips.write_pose_clip(str(tmp_path / f"{name}.usda"), name, joints, frames, pose, fps=30,
                                          blend_in_s=1.0, hold_s=2.0, blend_out_s=1.0)
        anchor = Gf.Vec3d(*info["posed"][pose["anchor"]])
        want = Gf.Vec3d(*pose["left"]["wrist_cm"])
        got_l = Gf.Vec3d(*info["posed"]["L_Wrist"]) - anchor
        got_r = Gf.Vec3d(*info["posed"]["R_Wrist"]) - anchor
        reach_ok = (Gf.Vec3d(*info["posed"]["L_Wrist"]) - Gf.Vec3d(0, 145, 0)).GetLength() < 50   # within arm length
        if reach_ok:
            assert (got_l - want).GetLength() < 1.0, (name, got_l)
            assert (got_r - Gf.Vec3d(-want[0], want[1], want[2])).GetLength() < 1.0, (name, got_r)  # mirrored
        assert info["start"] == [0, 30] and info["loop"] == [30, 90] and info["end"] == [90, 120]
        stage = Usd.Stage.Open(str(tmp_path / f"{name}.usda"))
        root = stage.GetPrimAtPath("/Root")
        assert root.IsA(UsdSkel.Animation) and root.GetAttribute("behavior:action:name").Get() == name
        tags = {c.GetAttribute("tag").Get(): (c.GetAttribute("start").Get(), c.GetAttribute("end").Get(),
                                              c.GetAttribute("track").Get()) for c in root.GetChildren()}
        assert tags == {name: (0, 120, 1), "ActionStart": (0, 30, 3), "ActionLoop": (30, 90, 2), "ActionEnd": (90, 120, 4)}
        assert "BehaviorActionAPI" in (root.GetMetadata("apiSchemas").GetAddedOrExplicitItems())
        anim = UsdSkel.Animation(root)
        first, hold = anim.GetRotationsAttr().Get(0), anim.GetRotationsAttr().Get(60)
        assert list(first) == list(frames[0][0])           # starts exactly at the idle pose
        assert list(hold) != list(first)                    # arms posed during the hold


def test_pose_clip_arms_twist_as_mirror_images(cfg):
    """Idle with one elbow bent sideways and the other almost straight (as in the motion library): both posed upper
    arms must still be mirror images, i.e. no extra twist on the straight-elbow side (wrung shoulder skin)."""
    pytest.importorskip("pxr")
    from pxr import Gf, UsdSkel
    from sdg_xray import pose_clips
    joints, frames = _library_like_skeleton()
    names = [j.split("/")[-1] for j in joints]
    rot, tr = frames[0]
    tr = list(tr)
    tr[names.index("L_Wrist")] = Gf.Vec3f(6, -24, 0)        # left elbow bent ~14 deg, to the side
    tr[names.index("R_Wrist")] = Gf.Vec3f(0, -24, 1.5)      # right elbow almost straight, bend plane forward
    parents = list(UsdSkel.Topology(joints).GetParentIndices())
    base = [pose_clips._local_matrix(r, t) for r, t in zip(rot, tr)]
    mirror = Gf.Matrix3d(-1, 0, 0, 0, 1, 0, 0, 0, 1)
    for name, pose in cfg["poses"]["arm_poses"].items():
        local = list(base)
        for i, m in pose_clips.posed_arm_locals(joints, parents, base, pose).items():
            local[i] = m
        world = pose_clips._fk(local, parents)
        left = world[names.index("L_UpArm")].ExtractRotationMatrix()
        right = world[names.index("R_UpArm")].ExtractRotationMatrix()
        diff = (mirror * left * mirror).GetTranspose() * right            # identity when mirror images
        angle = Gf.Rotation(Gf.Quatd(Gf.Matrix4d(1.0).SetRotate(diff).ExtractRotationQuat())).GetAngle()
        assert min(angle, 360 - angle) < 10, (name, angle)


def test_pose_config_rejected_when_malformed():
    with pytest.raises(ConfigError, match="wrist_cm"):
        load_config(CONFIG_DIR, {"poses.arm_poses.hands_on_head.left.wrist_cm": [1, 2]})


def test_sd_numbering_and_timeline(tmp_path):
    (tmp_path / "SD.00003").mkdir()
    (tmp_path / "other").mkdir()
    assert sdmod.next_sd_numbers(tmp_path, 2) == ["SD.00004", "SD.00005"]
    first, second = sdmod.create_run_dir(tmp_path / "sdg"), sdmod.create_run_dir(tmp_path / "sdg")
    assert first.name.startswith("run-") and second != first and second.name.startswith(first.name)  # same second: -2
    assert sdmod.next_sd_numbers(second, 1) == ["SD.00001"]                  # every run starts at SD.00001
    assert sdmod.timeline_path(tmp_path / "SD.00004", "CHEST", "R0001", False) == tmp_path / "SD.00004/CHEST/timeline.txt"
    assert sdmod.timeline_path(tmp_path / "SD.00004", "CHEST", "R0001", True) == tmp_path / "SD.00004/CHEST/R0001/timeline.txt"
    log = sdmod.Timeline(tmp_path / "SD.00004/CHEST/timeline.txt", {"sd": "SD.00004"})
    line = log.event(12.345, "Model loaded outside the room")
    log.close()
    text = (tmp_path / "SD.00004/CHEST/timeline.txt").read_text().splitlines()
    assert text[0] == "# sd: SD.00004" and text[-1] == "# status: ok"
    assert "t=   12.35s  Model loaded outside the room" in line


@pytest.mark.skipif(not any(DEFAULT_ROOMS_ROOT.glob("run-*")) or not any(DEFAULT_HUMANS_ROOT.glob("run-*")),
                    reason="no generated humans / rooms")
def test_real_inputs_plan(cfg):
    from sdg_xray.pipeline import build_jobs
    jobs = build_jobs(cfg)
    assert len(jobs["humans"]) == 2 and len(jobs["rooms"]) == 1
    for human in jobs["humans"]:
        assert 0.9 < human["chest_height_m"] < 1.6
    for steps in jobs["plans"].values():
        assert steps[0]["op"] == "spawn"


@pytest.mark.skipif(not any(DEFAULT_HUMANS_ROOT.glob("run-*")), reason="no generated humans")
def test_retarget_joints_exist_in_real_human(cfg):
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom, UsdSkel
    run = resolve_run(None, "humans", DEFAULT_HUMANS_ROOT)
    human = select_items(run, "humans", count=1)[0]
    stage = Usd.Stage.Open(human["usd"])
    skel = next(UsdSkel.Skeleton(p) for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton))
    leafs = {j.split("/")[-1] for j in skel.GetJointsAttr().Get()}
    missing = [j for j in cfg["retarget_mpfb"]["tags"].values() if j not in leafs]
    assert not missing


@pytest.mark.skipif(not any(DEFAULT_ROOMS_ROOT.glob("run-*")), reason="no generated rooms")
def test_fov_light_axis_matches_beam():
    """The FOV light is aimed along TubeHead +Y; check that this is the room's beam axis."""
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom, UsdSkel
    run = resolve_run(None, "rooms", DEFAULT_ROOMS_ROOT)
    room = select_items(run, "rooms", count=1)[0]
    meta = json.loads(Path(room["json"]).read_text())
    stage = Usd.Stage.Open(room["usd"])
    head = stage.GetPrimAtPath("/Room/Equipment/TubeStand/Carriage/Arm/TubeHead")
    window = stage.GetPrimAtPath("/Room/Equipment/TubeStand/Carriage/Arm/TubeHead/Collimator/LightWindow")
    assert head and window
    m = UsdGeom.Xformable(head).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    beam = m.TransformDir(Gf.Vec3d(0, 1, 0)).GetNormalized()
    want = Gf.Vec3d(*meta["anchors"]["stage"]["beam_axis"]).GetNormalized()
    assert Gf.Dot(beam, want) > 0.999


def test_compose_into_in_memory():
    pytest.importorskip("pxr")
    from pxr import Gf, Usd, UsdGeom, UsdSkel
    rooms = sorted(DEFAULT_ROOMS_ROOT.glob("run-*/rooms/R0001/R0001.usd"))
    if not rooms:
        pytest.skip("no generated rooms")
    sys.path.insert(0, str(REPO_ROOT / "room" / "isaac"))
    import compose_scene
    stage = Usd.Stage.CreateInMemory()
    info = compose_scene.compose_into(stage, rooms[-1], None, 1.25)
    assert stage.GetPrimAtPath("/World/Room/Markers/PatientStand").IsValid()
    assert math.isclose(info["detector_height_m"], 1.25, abs_tol=0.2)


def test_covered_skin_detection():
    """Skin under cloth (2 cm and 6 cm out) is covered; skin beyond the cloth's edge or under far cloth is not."""
    import numpy as np
    from sdg_xray import clothing
    xs = np.linspace(0.0, 0.4, 21)
    skin = np.array([[x, y, 0.0] for x in xs for y in (0.0, 0.1)])
    normals = np.tile([0.0, 0.0, 1.0], (len(skin), 1))
    def quad(x0, x1, z):     # two triangles over x in [x0, x1], y in [-0.05, 0.15]
        a, b, c, d = [x0, -0.05, z], [x1, -0.05, z], [x1, 0.15, z], [x0, 0.15, z]
        return np.array([[a, b, c], [a, c, d]], dtype=float)
    cloth = np.concatenate([quad(0.0, 0.1, 0.02), quad(0.1, 0.2, 0.06), quad(0.3, 0.4, 0.12)])
    covered = clothing.covered_vertices(skin, normals, cloth, max_dist_m=0.07)
    x = skin[:, 0]
    assert covered[x < 0.19].all()                          # 2 cm and 6 cm cloth (loose sleeve) cover the skin
    assert not covered[(x > 0.21) & (x < 0.29)].any()       # no cloth: skin stays
    assert not covered[x > 0.31].any()                      # cloth 12 cm away: too far, skin stays


def test_side_camera_balance_across_runs(tmp_path, cfg):
    """Each SD records one side camera; the dataset (all SDs, across runs) keeps the configured shares."""
    from sdg_xray.capture import cameras_for_sd, choose_group_options
    groups = {"side": {"LEFT": 0.5, "RIGHT": 0.5}}
    first = choose_group_options(tmp_path, groups, 2)
    assert sorted(p["side"] for p in first) == ["LEFT", "RIGHT"]           # 2 patients: one each
    for i, pick in enumerate(first):                                         # record them as a finished run
        sdmod.write_json(tmp_path / "run-20260101-000000" / f"SD.{i + 1:05d}" / "sd_info.json",
                         {"capture": {"groups": pick}})
    sdmod.write_json(tmp_path / "run-20260102-000000" / "SD.00001" / "sd_info.json",
                     {"capture": {"groups": {"side": "LEFT"}}})
    nxt = choose_group_options(tmp_path, groups, 1)                          # next run: 2 LEFT vs 1 RIGHT -> RIGHT
    assert nxt == [{"side": "RIGHT"}]
    skew = choose_group_options(tmp_path / "empty", {"side": {"LEFT": 0.75, "RIGHT": 0.25}}, 8)
    assert [p["side"] for p in skew].count("LEFT") == 6
    cams = {"cameras": {"FAR_LEFT": {"camera": "CeilingCam_FarLeft"}, "LEFT": {"rig": "L", "group": "side"},
                        "RIGHT": {"rig": "R", "group": "side"}}}
    names = [c["name"] for c in cameras_for_sd(cams, {"side": "RIGHT"})]
    assert "RIGHT" in names and "LEFT" not in names and "FAR_LEFT" in names


def test_capture_config_validation():
    with pytest.raises(ConfigError, match="not cameras of group"):
        load_config(CONFIG_DIR, {"capture.enabled": True, "capture.groups.side": {"LEFT": 0.5, "BACK": 0.5}})
    with pytest.raises(ConfigError, match="capture.fps must divide"):
        load_config(CONFIG_DIR, {"capture.enabled": True, "capture.fps": 4})
    with pytest.raises(ConfigError, match="disabled but has a share"):
        load_config(CONFIG_DIR, {"capture.enabled": True, "capture.cameras.LEFT.enabled": False})
    load_config(CONFIG_DIR, {"capture.enabled": True, "capture.cameras.LEFT.enabled": False,
                             "capture.groups.side.LEFT": 0})


def test_capture_fps_and_disabled_camera(cfg):
    from sdg_xray.capture import cameras_for_sd, every_n_frames
    assert cfg["capture"]["fps"] == 2 and every_n_frames(cfg) == 15        # 30 fps simulation -> every 15th frame
    cams = {"cameras": {"FAR_LEFT": {"camera": "CeilingCam_FarLeft"},
                        "CHECK_IN": {"camera": "CeilingCam_CheckIn", "enabled": False},
                        "FRONT": {"rig": "F", "enabled": True}, "LEFT": {"rig": "L", "group": "side"}}}
    picked = cameras_for_sd(cams, {"side": "LEFT"})
    assert [c["name"] for c in picked] == ["FAR_LEFT", "FRONT", "LEFT"]      # CHECK_IN: enabled: false
    assert all("enabled" not in c for c in picked)
