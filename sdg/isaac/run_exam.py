"""Runs inside Isaac Sim (python.sh): play X-ray exam visits of synthetic patients in generated rooms, live.

Started by scripts/run_pipeline.py with a job file:   <isaac>/python.sh isaac/run_exam.py --job job.json

Per visit (one human, one room, one exam) a new in-memory stage is built (nothing is saved):
  /World/Room                   room reference; detector + tube at the patient's T7 height (room/isaac/compose_scene.py)
  /World/HumanMotionLibrary     NVIDIA human motion library (omni.anim.behavior)
  /World/Patients/<id>          the synthetic human (payload) at the start point, an identity joint "SkelOrigin" inserted
                                above MPFB's root, BehaviorAgentAPI + retarget tags and axes (configs/retarget_mpfb.yaml)
  /World/NavMeshVolume          NavMesh over room, check-in room and the area outside the entrance (patient-sized agent,
                                5 cm sampling; set as this stage's navmeshSettings, Isaac preferences are not changed)
  .../TubeHead/FOVLight         collimator field light (RectLight + ShapingAPI along the beam)
The patient then performs the planned steps (sdg_xray/visit.py) through the behavior agent API: move_to per route point
(natural walking with NavMesh path finding), idle(facing) (turns in place), custom_action (the X-ray arm poses, as pose
clips added to the motion library, see sdg_xray/pose_clips.py), and the FOV light is switched. Every step is printed ("[xray] ...") and written to timeline.txt.
Any error prints "[xray] [ERROR] ...", marks the visit failed in sd_info.json and ends Isaac Sim with exit code 1.
"""

import argparse
import json
import shutil
import tempfile
import math
import sys
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

from sdg_xray import sd as sdmod  # noqa: E402  (no third-party imports)


class ExamError(RuntimeError):
    pass


def say(msg: str) -> None:
    print(f"[xray] {msg}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job", required=True, help="job JSON written by scripts/run_pipeline.py")
    return parser.parse_args()


ARGS = parse_args()
JOB = json.loads(Path(ARGS.job).read_text())
ISAAC = JOB["isaac"]
HEADLESS = bool(ISAAC.get("headless"))

from isaacsim import SimulationApp  # noqa: E402

say(f"Starting Isaac Sim ({'headless' if HEADLESS else 'GUI'})")
APP = SimulationApp({"headless": HEADLESS, "width": 1600, "height": 900, "anti_aliasing": 0})

import carb  # noqa: E402
import numpy as np  # noqa: E402
import omni.kit.app  # noqa: E402

if (JOB.get("capture") or {}).get("enabled") or ISAAC.get("debug_capture_dir"):
    for _key in ("/app/asyncRendering", "/app/asyncRenderingLowLatency", "/omni/replicator/asyncRendering"):
        carb.settings.get_settings().set(_key, False)     # each captured image belongs to the frame it is labelled with
if ISAAC.get("idle_animation_tags"):      # before the behavior extension starts
    carb.settings.get_settings().set("/exts/omni.anim.behavior.core/idleAnimationTags",
                                     [str(t) for t in ISAAC["idle_animation_tags"]])
_ext_manager = omni.kit.app.get_app().get_extension_manager()
for _ext in ISAAC.get("extensions") or []:
    if not _ext_manager.set_extension_enabled_immediate(_ext, True):
        say(f"[ERROR] extension {_ext} could not be enabled")
        APP.close()
        sys.exit(1)
# NavMesh: bake once on demand. Auto re-bake on every stage change (default on) re-bakes over the high-poly human
# while it loads and stalls the app for many minutes.
_settings = carb.settings.get_settings()
for _key in ("autoRebakeOnChanges", "vizGeomEnable", "vizSurfaceEnable", "vizOutlineEnable", "viewNavMesh"):
    _settings.set(f"/exts/omni.anim.navigation.core/navMesh/config/{_key}", False)     # session only, not saved
APP.update()

import omni.anim.behavior.core as bh  # noqa: E402
import omni.anim.behavior.schema as behavior_schema  # noqa: E402
import omni.anim.navigation.core as nav  # noqa: E402
import omni.kit.commands  # noqa: E402
import omni.timeline  # noqa: E402
import omni.usd  # noqa: E402
from omni.anim.navigation.core.scripts.command import NAVMESH_VOLUME_INCLUDE, CreateNavMeshVolumeCommand  # noqa: E402
from omni.anim.navigation.schema import NAV_MESH_EXCLUDE_API  # noqa: E402
from omni.anim.retarget.core.scripts.rig import RetargetRig  # noqa: E402
from omni.anim.retarget.core.scripts.utils import set_forward_axis, set_up_axis  # noqa: E402
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdSkel, Vt  # noqa: E402

from sdg_xray import clothing, fov_ies, pose_clips  # noqa: E402

sys.path.insert(0, str(Path(JOB["compose_scene"]).parent))
import compose_scene  # noqa: E402  (room/isaac/compose_scene.py)

FPS = float(ISAAC.get("fps", 30))
REALTIME = bool(ISAAC.get("realtime", True)) and not HEADLESS
SEQ = JOB["sequence"]
TASK_TIMEOUT_S = float(SEQ.get("task_timeout_s", 90))
DEBUG_HANDS = bool(JOB.get("debug_hands"))
TUBE_HEAD = "/World/Room/Equipment/TubeStand/Carriage/Arm/TubeHead"
MOTION_LIB_PATH = "/World/HumanMotionLibrary"
POSE_CLIPS = {}       # arm pose name -> {action, file, anchor, wrist_offsets}; built once per run
LIB_TO_TAG = {"Pelvis": "Hips", "Head": "Head", "Chest": "Chest", "Neck1": "Neck1", "Spine1": "Spine1"}
LIB_HEAD_M = 1.65     # library rig Head joint height (m), updated when the clips are built
CLIP_DIR = Path(tempfile.mkdtemp(prefix="sdg_pose_clips_"))
UP = Gf.Vec3d(0, 0, 1)

timeline = omni.timeline.get_timeline_interface()
behavior = bh.acquire_interface()
TASK_ERRORS = {}      # task id -> BehaviorTaskError code from the task-ended event


def _on_task_ended(event):
    try:
        payload = event.payload if hasattr(event, "payload") else event
        error = payload["task_error"]
        try:
            error = bh.BehaviorTaskError(error).name
        except Exception:
            pass
        TASK_ERRORS[payload["task_id"]] = error
    except Exception:
        pass


import carb.eventdispatcher  # noqa: E402

_task_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
    observer_name="sdg", event_name=bh.GLOBAL_EVENT_BEHAVIOR_TASK_ENDED, on_event=_on_task_ended)
navmesh = nav.acquire_interface()
_last_tick = [time.perf_counter()]
FRAME_HOOKS = []      # called after every simulated frame (debug capture)


# ----------------------------------------------------------------------------------------------------------------- utils
def tick(frames: int = 1) -> None:
    """Advance the app (and the playing timeline) by `frames` frames; at wall-clock speed in GUI real-time mode."""
    for _ in range(frames):
        APP.update()
        if REALTIME:
            wait = 1.0 / FPS - (time.perf_counter() - _last_tick[0])
            if wait > 0:
                time.sleep(wait)
        _last_tick[0] = time.perf_counter()
        if FRAME_HOOKS:
            for hook in FRAME_HOOKS:
                hook()
        if not APP.is_running():
            raise ExamError("Isaac Sim window was closed")


def sim_time() -> float:
    return float(timeline.get_current_time())


def f3(v):
    return carb.Float3(float(v[0]), float(v[1]), float(v[2]))


def v3(c):
    return Gf.Vec3d(c.x, c.y, c.z)


def wait_loaded(check, what: str, timeout_s: float) -> None:
    start = time.time()
    while not check():
        if time.time() - start > timeout_s:
            raise ExamError(f"{what}: not loaded after {timeout_s:.0f} s")
        APP.update()


# ----------------------------------------------------------------------------------------------------------------- stage
def build_stage(visit: dict):
    """New stage with room, motion library, patient agent, navmesh and FOV light. Returns (stage, skelroot path)."""
    human, room = visit["human"], visit["room"]
    ctx = omni.usd.get_context()
    if not ctx.new_stage():
        raise ExamError("could not create a new stage")
    APP.update()
    stage = ctx.get_stage()
    say(f"  stage: room {room['id']} ({room['usd']})")
    info = compose_scene.compose_into(stage, room["usd"], None, human["chest_height_m"])
    wait_loaded(lambda: stage.GetPrimAtPath("/World/Room/Markers/PatientStand").IsValid(), "room", 120)
    say(f"  stage: detector and tube at {info.get('detector_height_m')} m (patient T7)")

    omni.kit.commands.execute("CreatePayloadCommand", usd_context=ctx, path_to=Sdf.Path(MOTION_LIB_PATH),
                              asset_path=ISAAC["motion_library"], prim_path=None, instanceable=False, select_prim=False)

    def motion_lib_ready():
        prim = stage.GetPrimAtPath(MOTION_LIB_PATH)
        return prim.IsValid() and prim.IsA(behavior_schema.BEHAVIOR_MOTION_LIBRARY) and bool(prim.GetChildren())

    wait_loaded(motion_lib_ready, f"motion library {ISAAC['motion_library']}", float(ISAAC.get("startup_timeout_s", 600)))
    say("  stage: motion library loaded")
    register_pose_clips(stage)

    skelroot = add_patient(stage, human, visit["steps"][0])
    add_navmesh(stage)
    add_fov_light(stage)
    add_outside_light(stage, visit["steps"][0])
    return stage, skelroot


def build_pose_clips(stage) -> None:
    """Once per run: one custom-action clip per arm pose of poses.yaml, built from the library's Idle clip."""
    global LIB_HEAD_M
    idle_prim = stage.GetPrimAtPath(f"{MOTION_LIB_PATH}/BuiltinActions/Idle/Idle")
    wait_loaded(lambda: idle_prim.IsValid() and idle_prim.IsA(UsdSkel.Animation), "motion library Idle clip", 120)
    joints, frames = pose_clips.read_idle(UsdSkel.Animation(idle_prim))
    timing = JOB["timing"]
    for name, pose in JOB["arm_poses"].items():
        action = "Xray" + "".join(part.capitalize() for part in name.split("_"))
        path = CLIP_DIR / f"{action}.usda"
        try:
            info = pose_clips.write_pose_clip(str(path), action, joints, frames, pose, fps=FPS,
                                              blend_in_s=float(timing.get("arms_up_s", 2.0)), hold_s=2.0,
                                              blend_out_s=float(timing.get("arms_down_s", 1.2)))
        except pose_clips.ClipError as exc:
            raise ExamError(f"arm pose {name}: {exc}")
        posed = info["posed"]
        anchor = posed["Head"] if pose.get("anchor", "Head") == "Head" else posed["Pelvis"]
        offsets = {side: [posed[w][i] - anchor[i] for i in range(3)] for side, w in (("left", "L_Wrist"), ("right", "R_Wrist"))}
        POSE_CLIPS[name] = {"action": action, "file": str(path), "anchor": pose.get("anchor", "Head"), "wrist_offsets": offsets}
        LIB_HEAD_M = posed["Head"][1] / 100.0
        say(f"  pose clip {action}: {info['frames']} frames, hold {info['loop']}, wrists "
            f"L {tuple(round(v) for v in offsets['left'])} R {tuple(round(v) for v in offsets['right'])} cm from "
            f"{pose.get('anchor', 'Head')}")


def register_pose_clips(stage) -> None:
    """Add the pose clips as custom actions to this stage's motion library (before Play: agents read it then)."""
    if not POSE_CLIPS:
        build_pose_clips(stage)
    scope = f"{MOTION_LIB_PATH}/CustomActions"
    stage.DefinePrim(scope, "Scope")
    stage.DefinePrim(f"{scope}/Xray", "Scope")
    for clip in POSE_CLIPS.values():
        prim = stage.DefinePrim(f"{scope}/Xray/{clip['action']}")
        prim.GetPayloads().AddPayload(clip["file"])
        prim.CreateRelationship("animationSkelBinding:sourceSkeleton").SetTargets([Sdf.Path(f"{MOTION_LIB_PATH}/Skeleton")])
    APP.update()
    say(f"  stage: pose actions {', '.join(c['action'] for c in POSE_CLIPS.values())} added to the motion library")


def add_patient(stage, human: dict, spawn: dict) -> Sdf.Path:
    """The human, placed at the spawn step's position and facing before Play (the agent is created there)."""
    holder = stage.DefinePrim(f"/World/Patients/{human['id']}", "Xform")
    holder.GetPayloads().AddPayload(human["usd"])
    if spawn.get("op") == "spawn":
        xf = UsdGeom.Xformable(holder)
        xf.AddTranslateOp().Set(Gf.Vec3d(*spawn["position"]))
        f = spawn["facing"]
        xf.AddRotateZOp().Set(math.degrees(math.atan2(f[1], f[0])) + 90.0)   # human front (-Y) onto `facing`
    wait_loaded(lambda: any(p.IsA(UsdSkel.Skeleton) for p in Usd.PrimRange(holder)), f"human {human['id']}", 120)
    skelroots = [p for p in Usd.PrimRange(holder) if p.IsA(UsdSkel.Root)]
    skeletons = [p for p in Usd.PrimRange(holder) if p.IsA(UsdSkel.Skeleton)]
    if len(skelroots) != 1 or len(skeletons) != 1:
        raise ExamError(f"human {human['id']}: expected 1 SkelRoot and 1 Skeleton, found {len(skelroots)} / {len(skeletons)}")
    skelroot, skel = skelroots[0], UsdSkel.Skeleton(skeletons[0])
    add_identity_root(skelroot, skel, JOB.get("root_joint_name", "SkelOrigin"))
    if ISAAC.get("hide_anatomy", True):
        hidden = 0
        for prim in Usd.PrimRange(skelroot):
            if prim.GetName().startswith("bone_") and prim.IsA(UsdGeom.Imageable):
                UsdGeom.Imageable(prim).MakeInvisible()
                hidden += 1
        say(f"  stage: {hidden} anatomical bone meshes hidden (isaac.hide_anatomy)")
    body = next((p for p in Usd.PrimRange(skelroot) if p.IsA(UsdGeom.Mesh) and p.GetName() == "base"), None)
    if body is not None and ISAAC.get("debug_clear_body_holes"):          # debugging: render the full body
        UsdGeom.Mesh(body).GetHoleIndicesAttr().Set([])
    body_holes = UsdGeom.Mesh(body).GetHoleIndicesAttr().Get() if body is not None else None
    if body_holes is not None and len(body_holes):
        say(f"  stage: the human model already hides {len(body_holes)} body faces under its clothing")
    elif ISAAC.get("hide_body_under_clothes", True) and human.get("clothing"):
        info = clothing.hide_body_under_clothes(skelroot, human["clothing"],
                                                max_dist_m=float(ISAAC.get("clothing_reach_m", 0.07)))
        say(f"  stage: {info['removed']}/{info['faces']} body faces under clothing hidden "
            f"({', '.join(info['garments']) or 'no garments found'})")
    APP.update()

    skelroot.ApplyAPI(behavior_schema.BEHAVIOR_AGENT_API)
    skelroot.GetRelationship("behavior:motionLibrary").SetTargets([Sdf.Path(MOTION_LIB_PATH)])
    retarget(skel, human["id"])
    omni.kit.commands.execute("ApplyNavMeshAPICommand", prim_path=skelroot.GetPath(), api=NAV_MESH_EXCLUDE_API)
    APP.update()
    say(f"  stage: patient {human['id']} ({human.get('height_cm')} cm) is a behavior agent")
    return skelroot.GetPath()


def add_identity_root(skelroot, skel, name: str) -> None:
    """MPFB's root joint sits at the pelvis. The retargeter needs Hips below a root joint and the behavior system
    needs the skeleton root at the origin, so insert an identity joint above it (skeleton, per-joint primvars and
    every skinned mesh's skel:joints; in the in-memory stage only). `name` must not be "root" in any case."""
    joints = list(skel.GetJointsAttr().Get())
    if joints[0] == name:
        return
    skel.GetJointsAttr().Set([name] + [f"{name}/{j}" for j in joints])
    for attr in (skel.GetBindTransformsAttr(), skel.GetRestTransformsAttr()):
        attr.Set([Gf.Matrix4d(1.0)] + list(attr.Get()))
    lengths = skel.GetPrim().GetAttribute("primvars:blender:bone_lengths")
    if lengths and lengths.Get() is not None and len(lengths.Get()) == len(joints):
        lengths.Set([0.1] + list(lengths.Get()))
    for prim in Usd.PrimRange(skelroot):
        if prim.IsA(UsdGeom.Mesh) and prim.HasAPI(UsdSkel.BindingAPI):
            binding = UsdSkel.BindingAPI(prim)
            own = binding.GetJointsAttr()
            source = list(own.Get()) if own and own.HasAuthoredValue() else joints
            binding.CreateJointsAttr().Set([f"{name}/{j}" for j in source])


def retarget(skel, human_id: str) -> None:
    tags = JOB["retarget_tags"]
    leafs = {j.split("/")[-1] for j in skel.GetJointsAttr().Get()}
    missing = sorted(j for j in tags.values() if j not in leafs)
    if missing:
        raise ExamError(f"human {human_id}: retarget joints missing in the skeleton: {', '.join(missing)}")
    rig = RetargetRig(ISAAC.get("motion_library_rig", "Human"))
    rig.set_skeleton(skel)
    rig.set_joint_mappings(tags)
    set_up_axis(skel, JOB.get("up_axis", "Z"))
    set_forward_axis(skel, JOB.get("forward_axis", "MINUS Y"))
    if not rig.auto_setup(use_mapping=False, auto_facing=False, auto_tagging=False, auto_posing=True):
        raise ExamError(f"human {human_id}: retarget set-up (retarget pose) failed")
    mapped = rig.get_tag_joint_mapping()
    if len(mapped) < len(tags):
        raise ExamError(f"human {human_id}: only {len(mapped)}/{len(tags)} retarget tags applied")
    success, _, template = rig.get_reference_skeleton()
    if not success:
        raise ExamError("reference skeleton of the retarget rig not found")
    set_tpose_retarget_pose(skel, tags, str(template), human_id)


# Tagged segments whose direction is matched to the reference rig's T-pose (parent before child).
# Spine and neck stay as authored: MPFB's are upright like the reference, and re-aiming them tilts the head back.
TPOSE_SEGMENTS = [
    seg for s in ("Left", "Right") for seg in (
        (f"{s}Shoulder", f"{s}Arm"), (f"{s}Arm", f"{s}ForeArm"), (f"{s}ForeArm", f"{s}Hand"),
        (f"{s}Hand", f"{s}HandMiddle2"), (f"{s}Leg", f"{s}Shin"), (f"{s}Shin", f"{s}Foot"), (f"{s}Foot", f"{s}ToeBase"))]


def _skel_fk(local, parents):
    world = [None] * len(local)
    for i, parent in enumerate(parents):
        world[i] = Gf.Matrix4d(local[i]) * world[parent] if parent >= 0 else Gf.Matrix4d(local[i])
    return world


def _reference_tag_positions(template: str) -> dict:
    """Tag -> rest position of the retarget rig's reference skeleton (a T-pose), in the MPFB frame (Z up, -Y front)."""
    ref_stage = Usd.Stage.Open(template)
    ref = next(UsdSkel.Skeleton(p) for p in ref_stage.Traverse() if p.IsA(UsdSkel.Skeleton))
    joints = list(ref.GetJointsAttr().Get())
    pose_attr = ref.GetPrim().GetAttribute("controlRig:retargetTransforms")
    pose = list(pose_attr.Get()) if pose_attr and pose_attr.Get() else list(ref.GetRestTransformsAttr().Get())
    world = _skel_fk(pose, list(UsdSkel.Topology(joints).GetParentIndices()))
    # the reference rig's joints are named as in its "Default" automap: [tag, joint] pairs
    automap = Path(template).parent.parent / "automap" / "Default.automap.json"
    if not automap.exists():
        raise ExamError(f"reference automap not found: {automap}")
    tag_to_joint = {tag: joint for tag, joint in json.loads(automap.read_text())["mappings"] if tag and joint}
    leaf_index = {j.split("/")[-1]: i for i, j in enumerate(joints)}
    pos = {tag: world[leaf_index[j]].ExtractTranslation() for tag, j in tag_to_joint.items() if j in leaf_index}
    y_up = UsdGeom.GetStageUpAxis(ref_stage) == UsdGeom.Tokens.y
    to_mpfb = (lambda v: Gf.Vec3d(v[0], -v[2], v[1])) if y_up else (lambda v: Gf.Vec3d(v))
    out = {tag: to_mpfb(v) for tag, v in pos.items()}
    if out["LeftToeBase"][1] > out["LeftFoot"][1]:      # toes must point to the front (-Y); flip if the rig faces -Z
        out = {tag: Gf.Vec3d(v[0], -v[1], v[2]) for tag, v in out.items()} if y_up else out
    if out["LeftArm"][0] < out["RightArm"][0]:           # patient's left = +X
        raise ExamError("reference skeleton: unexpected left/right orientation")
    return out


def set_tpose_retarget_pose(skel, tags: dict, template: str, human_id: str) -> None:
    """MPFB humans rest in an A-pose (arms ~45 deg down, forearms angled forward); the motion library's reference rig
    is a T-pose, and the retargeter's auto-posing leaves MPFB unchanged, so every motion would be transferred relative
    to the wrong posture (raised, bent forearms). Author the retarget pose (controlRig:retargetTransforms) ourselves:
    rotate each tagged segment onto the reference T-pose direction and roll the hands to the same palm orientation."""
    ref = _reference_tag_positions(template)
    joints = list(skel.GetJointsAttr().Get())
    parents = list(UsdSkel.Topology(joints).GetParentIndices())
    index = {j.split("/")[-1]: i for i, j in enumerate(joints)}
    tag_index = {tag: index[leaf] for tag, leaf in tags.items() if leaf in index}
    local = [Gf.Matrix4d(m) for m in skel.GetRestTransformsAttr().Get()]

    def rotate_joint(i, rotation, world):
        p = world[i].ExtractTranslation()
        moved = world[i] * Gf.Matrix4d(1.0).SetTranslate(-p) * Gf.Matrix4d(1.0).SetRotate(rotation) * \
            Gf.Matrix4d(1.0).SetTranslate(p)
        local[i] = moved * world[parents[i]].GetInverse() if parents[i] >= 0 else moved

    for a, b in TPOSE_SEGMENTS:
        if a not in tag_index or b not in tag_index or a not in ref or b not in ref:
            continue
        world = _skel_fk(local, parents)
        cur = world[tag_index[b]].ExtractTranslation() - world[tag_index[a]].ExtractTranslation()
        want = ref[b] - ref[a]
        if cur.GetLength() < 1e-6 or want.GetLength() < 1e-6:
            continue
        rotate_joint(tag_index[a], Gf.Rotation(cur, want), world)
        if a.endswith("Hand"):                       # palm: index -> pinky knuckles like the reference
            side = a[:-4]
            i2, p2 = f"{side}HandIndex2", f"{side}HandPinky2"
            if all(t in tag_index and t in ref for t in (i2, p2)):
                world = _skel_fk(local, parents)
                axis = want.GetNormalized()
                cur2 = world[tag_index[p2]].ExtractTranslation() - world[tag_index[i2]].ExtractTranslation()
                want2 = ref[p2] - ref[i2]
                cur2, want2 = cur2 - axis * Gf.Dot(cur2, axis), want2 - axis * Gf.Dot(want2, axis)
                if cur2.GetLength() > 1e-6 and want2.GetLength() > 1e-6:
                    rotate_joint(tag_index[a], Gf.Rotation(cur2, want2), world)
    world = _skel_fk(local, parents)
    worst = 0.0
    for a, b in TPOSE_SEGMENTS:
        if a in tag_index and b in tag_index and a in ref and b in ref:
            cur = (world[tag_index[b]].ExtractTranslation() - world[tag_index[a]].ExtractTranslation()).GetNormalized()
            worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, Gf.Dot(cur, (ref[b] - ref[a]).GetNormalized()))))))
    skel.GetPrim().GetAttribute("controlRig:retargetTransforms").Set(Vt.Matrix4dArray(local))
    say(f"  stage: retarget pose = reference T-pose (largest segment deviation {worst:.1f} deg)")


NAVMESH_AGENT = {   # isaac.yaml navmesh key -> navigation setting (cm)
    "agent_min_radius_m": "agentMinRadius", "agent_max_radius_m": "agentMaxRadius", "agent_min_height_m": "agentMinHeight",
    "agent_max_step_height_m": "agentMaxStepHeight", "agent_min_island_radius_m": "agentMinIslandRadius",
    "sampling_distance_m": "agentSamplingDistance",
}


def add_navmesh(stage) -> None:
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    box = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/Room")).ComputeAlignedRange()
    cfg = ISAAC.get("navmesh") or {}
    # Agent size / sampling as stage navmesh settings (this in-memory stage only; Isaac's saved preferences are
    # untouched). The navigation extension reads them from the root layer's customLayerData, in cm.
    nav_settings = {setting: float(cfg[key]) * 100.0 for key, setting in NAVMESH_AGENT.items() if cfg.get(key) is not None}
    nav_settings["autoRebakeOnChanges"] = False
    layer = stage.GetRootLayer()
    data = dict(layer.customLayerData)
    data["navmeshSettings"] = dict(data.get("navmeshSettings", {}), **nav_settings)
    layer.customLayerData = data
    for setting, value in nav_settings.items():
        _settings.set(f"/exts/omni.anim.navigation.core/navMesh/config/{setting}", value)
    margin, height = float(cfg.get("margin_m", 3.0)), float(cfg.get("height_m", 2.4))
    lo, hi = box.GetMin(), box.GetMax()
    CreateNavMeshVolumeCommand(parent_prim_path=Sdf.Path("/World"), volume_type=NAVMESH_VOLUME_INCLUDE).do()
    volume = UsdGeom.Xformable(stage.GetPrimAtPath("/World/NavMeshVolume"))
    volume.ClearXformOpOrder()
    volume.AddTranslateOp().Set(Gf.Vec3d((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, height / 2 - 0.1))
    volume.AddScaleOp().Set(Gf.Vec3d(hi[0] - lo[0] + 2 * margin, hi[1] - lo[1] + 2 * margin, height))
    if stage.GetPrimAtPath("/World/Room/Corridor"):            # the room has its own corridor floor
        return
    floor = UsdGeom.Mesh.Define(stage, "/World/OutsideFloor")   # walkable ground outside the suite
    x0, y0, x1, y1 = lo[0] - margin, lo[1] - margin, hi[0] + margin, hi[1] + margin
    floor.CreatePointsAttr([(x0, y0, -0.002), (x1, y0, -0.002), (x1, y1, -0.002), (x0, y1, -0.002)])
    floor.CreateFaceVertexCountsAttr([4])
    floor.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    floor.CreateDisplayColorAttr([(0.55, 0.56, 0.58)])
    UsdPhysics.CollisionAPI.Apply(floor.GetPrim())               # the NavMesh is baked from collision geometry


FOV_LIGHT = f"{TUBE_HEAD}/Collimator/FOVLight"


def add_fov_light(stage) -> None:
    """The room's collimator field light (Collimator/FOVLight, IES rectangle, invisible until an exposure). Rooms built
    before the room pipeline had it get the same light here, from sequence.yaml -> fov_light."""
    light_cfg = SEQ.get("fov_light") or {}
    if not light_cfg.get("enabled", True):
        return
    existing = stage.GetPrimAtPath(FOV_LIGHT)
    if existing and existing.GetTypeName().endswith("Light"):
        if light_cfg.get("intensity_override"):
            existing.GetAttribute("inputs:intensity").Set(float(light_cfg["intensity_override"]))
        UsdGeom.Imageable(existing).MakeInvisible()
        say("  stage: collimator FOV light from the room")
        return
    head = stage.GetPrimAtPath(TUBE_HEAD)
    window = stage.GetPrimAtPath(f"{TUBE_HEAD}/Collimator/LightWindow")
    if not head or not window:
        raise ExamError(f"room has no {TUBE_HEAD}/Collimator/LightWindow (FOV light)")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_])
    centre = cache.ComputeRelativeBound(window, head).ComputeAlignedRange().GetMidpoint()
    sid = stage.GetPrimAtPath(f"{TUBE_HEAD}/FocalSpot").GetAttribute("sdg:sid_m").Get() or 1.5
    w_cm, h_cm = light_cfg.get("field_cm", [35, 43])
    ies = CLIP_DIR / "fov_field.ies"
    fov_ies.write_rect_ies(ies, math.degrees(math.atan(w_cm / 200.0 / sid)), math.degrees(math.atan(h_cm / 200.0 / sid)))
    light = UsdLux.DiskLight.Define(stage, FOV_LIGHT)
    xf = UsdGeom.Xformable(light)
    xf.AddTranslateOp().Set(Gf.Vec3d(centre[0], centre[1] + 0.03, centre[2]))
    xf.AddRotateXOp().Set(90.0)                                   # emits along -Z -> along TubeHead +Y (the beam)
    light.CreateRadiusAttr(0.01)
    light.CreateColorAttr(Gf.Vec3f(*light_cfg.get("color", [1.0, 0.96, 0.82])))
    light.CreateIntensityAttr(float(light_cfg.get("intensity", 150000)))
    shaping = UsdLux.ShapingAPI.Apply(light.GetPrim())
    shaping.CreateShapingIesFileAttr(Sdf.AssetPath(str(ies)))
    shaping.CreateShapingIesNormalizeAttr(False)
    UsdGeom.Imageable(light).MakeInvisible()
    say("  stage: collimator FOV light added (room has none)")


def add_outside_light(stage, spawn: dict) -> None:
    """The room pipeline lights only the suite; light the area outside the entrance where the patient arrives and
    leaves with a copy of one of the room's own ceiling panels (same size, intensity, colour temperature)."""
    cfg = SEQ.get("outside_light") or {}
    if not cfg.get("enabled", True) or spawn.get("op") != "spawn":
        return
    if stage.GetPrimAtPath("/World/Room/Corridor/Light"):      # the room lights its corridor itself
        say("  stage: corridor light from the room")
        return
    panel = next((UsdLux.RectLight(p) for p in Usd.PrimRange(stage.GetPrimAtPath("/World/Room/Lights"))
                  if p.IsA(UsdLux.RectLight)), None)
    light = UsdLux.RectLight.Define(stage, "/World/OutsideLight")
    pos, facing = spawn["position"], spawn["facing"]
    ahead = float(cfg.get("towards_door_m", 0.6))
    UsdGeom.Xformable(light).AddTranslateOp().Set(
        Gf.Vec3d(pos[0] + facing[0] * ahead, pos[1] + facing[1] * ahead, float(cfg.get("height_m", 2.6))))
    if panel is not None:
        for name in ("Intensity", "Width", "Height", "ColorTemperature", "EnableColorTemperature", "Exposure", "Normalize"):
            value = getattr(panel, f"Get{name}Attr")().Get()
            if value is not None:
                getattr(light, f"Create{name}Attr")(value)
    else:
        light.CreateIntensityAttr(3000.0)
        light.CreateWidthAttr(1.2)
        light.CreateHeightAttr(0.6)
    if cfg.get("intensity_scale", 1.0) != 1.0:
        light.GetIntensityAttr().Set(light.GetIntensityAttr().Get() * float(cfg["intensity_scale"]))
    say("  stage: corridor light outside the entrance (copy of a room ceiling panel)")


def set_fov_light(stage, on: bool) -> None:
    prim = stage.GetPrimAtPath(FOV_LIGHT)
    if prim:
        (UsdGeom.Imageable(prim).MakeVisible if on else UsdGeom.Imageable(prim).MakeInvisible)()


def check_route(steps) -> None:
    """Every walk segment must have a NavMesh path; name the first blocked one (e.g. a door too narrow)."""
    mesh = navmesh.get_navmesh()
    if mesh is None:
        raise ExamError("no NavMesh after baking")
    points = [("start", steps[0]["position"])] if steps and steps[0]["op"] == "spawn" else []
    for step in steps:
        if step["op"] == "walk":
            points += [(step["target"], p) for p in step["waypoints"]]
    for (name_a, a), (name_b, b) in zip(points, points[1:]):
        pa, island_a = mesh.query_closest_point(target=f3(a))
        pb, island_b = mesh.query_closest_point(target=f3(b))
        for name, want, got in ((name_a, a, pa), (name_b, b, pb)):
            if got is not None and math.hypot(got.x - want[0], got.y - want[1]) > 0.25:
                raise ExamError(f"route point {name} {tuple(round(v, 2) for v in want[:2])} is not on the NavMesh "
                                f"(nearest walkable {got.x:.2f}, {got.y:.2f}); room too tight for the agent radius?")
        path = mesh.query_shortest_path(start_pos=pa, end_pos=pb) if pa is not None and pb is not None else None
        points_on_path = path.get_points() if path is not None and hasattr(path, "get_points") else path
        if not points_on_path:
            raise ExamError(f"no NavMesh path from {name_a} {tuple(round(v, 2) for v in a[:2])} to {name_b} "
                            f"{tuple(round(v, 2) for v in b[:2])} (door too narrow / blocked?)")
        end = v3(points_on_path[-1]) if not isinstance(points_on_path[-1], Gf.Vec3d) else points_on_path[-1]
        if math.hypot(end[0] - b[0], end[1] - b[1]) > 0.3:
            raise ExamError(f"NavMesh path from {name_a} ends {math.hypot(end[0] - b[0], end[1] - b[1]):.2f} m short of "
                            f"{name_b} {tuple(round(v, 2) for v in b[:2])} (door too narrow / blocked?)")
    say(f"  stage: NavMesh route checked ({len(points) - 1} segments)")


# ----------------------------------------------------------------------------------------------------------------- agent
class Patient:
    def __init__(self, stage, skelroot: Sdf.Path, human: dict):
        self.stage, self.human = stage, human
        self.agent = None
        for _ in range(int(5 * FPS)):
            self.agent = behavior.get_agent(str(skelroot))
            if self.agent is not None:
                break
            tick()
        if self.agent is None:
            raise ExamError(f"behavior agent for {skelroot} was not created (motion library / retarget / navmesh)")
        height = self.agent.get_height() * UsdGeom.GetStageMetersPerUnit(stage)
        if not 0.5 < height < 2.5:
            raise ExamError(f"behavior agent height {height:.2f} m is implausible (retarget up/forward axes wrong?)")
        mpu = UsdGeom.GetStageMetersPerUnit(stage)
        radius = self.agent.get_radius() * mpu
        say(f"  agent ready: height {height:.2f} m, radius {radius:.2f} m, arm length {self.agent.get_arm_length() * mpu:.2f} m")
        max_radius = (ISAAC.get("navmesh") or {}).get("agent_max_radius_m")
        if max_radius and radius > float(max_radius):
            raise ExamError(f"agent radius {radius:.2f} m exceeds isaac.navmesh.agent_max_radius_m = {max_radius}")
        speed = SEQ.get("walk_speed_mps")
        if speed:
            self.agent.set_speed(float(speed) / UsdGeom.GetStageMetersPerUnit(stage))   # stage units per second
        self.action_task = None

    def position(self) -> Gf.Vec3d:
        return v3(self.agent.get_world_translation())

    def facing(self) -> Gf.Vec3d:
        f = v3(self.agent.get_facing_direction())
        f[2] = 0.0
        return f.GetNormalized()

    def run_task(self, task_id, what: str, max_s: float = None):
        if task_id == bh.BEHAVIOR_TASK_ID_INVALID:
            raise ExamError(f"{what}: the behavior system rejected the task")
        limit = int((max_s or TASK_TIMEOUT_S) * FPS)
        for _ in range(limit):
            tick()
            status = self.agent.get_task_status(task_id)
            if status != bh.BehaviorTaskStatus.RUNNING:
                if status != bh.BehaviorTaskStatus.SUCCEEDED:
                    error = TASK_ERRORS.get(task_id)
                    raise ExamError(f"{what}: task ended with {status}"
                                    f"{f' (error {error})' if error not in (None, 0) else ''} at {self._where()}")
                return
        self.agent.cancel_task(task_id)
        raise ExamError(f"{what}: not finished after {limit / FPS:.0f} s (patient stuck at {self._where()})")

    def _where(self) -> str:
        p = self.position()
        return f"({p[0]:.2f}, {p[1]:.2f})"

    def body_to_world(self, v, point: bool):
        """Body frame (+X left, -Y front, +Z up) -> stage."""
        front = self.facing()
        left = Gf.Vec3d(-front[1], front[0], 0.0)
        out = left * v[0] + front * (-v[1]) + UP * v[2]
        return out + self.position() if point else out

    # ---------------------------------------------------------------- ops
    def spawn(self, step):
        """The patient prim was placed at the spawn point before Play; teleport only if the agent is elsewhere."""
        target = step["position"]
        if math.hypot(self.position()[0] - target[0], self.position()[1] - target[1]) > 0.3:
            task = self.agent.teleport(target=f3(target), facing=f3(step["facing"]))
            if task == bh.BEHAVIOR_TASK_ID_INVALID:
                raise ExamError("teleport to the start position was rejected")
        tick(int(0.5 * FPS))
        dist = math.hypot(self.position()[0] - target[0], self.position()[1] - target[1])
        if dist > 0.3:
            raise ExamError(f"patient is {dist:.2f} m from the start point outside the entrance at {self._where()} "
                            "(start point off the NavMesh?)")

    def start_idle(self, facing=None):
        """idle() has no duration: it runs until the next locomotion task replaces it."""
        task = self.agent.idle(facing=f3(facing)) if facing else self.agent.idle()
        if task == bh.BEHAVIOR_TASK_ID_INVALID:
            raise ExamError("idle was rejected by the behavior system")
        return task

    def idle(self, step):
        if not step.get("keep_arms"):          # holding a pose: no new task, the pose action keeps running
            self.start_idle(step.get("facing"))
        tick(max(1, int(round(step["duration"] * FPS))))

    def walk(self, step):
        """NavMesh path finding to each waypoint in turn (around door leaves and furniture); brake only at the end."""
        target = step["waypoints"][-1]
        last = len(step["waypoints"]) - 1
        for k, point in enumerate(step["waypoints"]):
            self.run_task(self.agent.move_to(target=f3(point), auto_brake=(k == last)),
                          f"walk to {step['target']} (point {k + 1}/{last + 1} at {point[0]:.2f}, {point[1]:.2f})")
        dist = math.hypot(self.position()[0] - target[0], self.position()[1] - target[1])
        if dist > float(SEQ.get("arrive_tolerance_m", 0.25)):
            raise ExamError(f"walk to {step['target']}: ended {dist:.2f} m from the target at {self._where()}")

    def facing_error_deg(self, facing) -> float:
        want = Gf.Vec3d(*facing).GetNormalized()
        return math.degrees(math.acos(max(-1.0, min(1.0, Gf.Dot(self.facing(), want)))))

    def turn(self, step):
        """Idle with a facing direction: the agent turns in place; wait until it faces it (at least `duration`)."""
        self.start_idle(step["facing"])
        frames, min_frames, limit = 0, int(step["duration"] * FPS), int((step["duration"] + 10.0) * FPS)
        while frames < min_frames or self.facing_error_deg(step["facing"]) > 8.0:
            tick()
            frames += 1
            if frames > limit:
                raise ExamError(f"turn: still {self.facing_error_deg(step['facing']):.0f} deg off after "
                                f"{limit / FPS:.0f} s at {self._where()}")
        tick(int(float(step.get("settle", 0.0)) * FPS))

    def arms(self, step):
        """Arm poses are custom actions (pose clips, see sdg_xray/pose_clips.py). "arms up" plays the clip for the
        whole time in the pose (blend in + hold through the FOV light); "down" waits for its blend-out to finish."""
        if step["pose"] == "down":
            frames, limit = 0, int((step["duration"] + 5.0) * FPS)
            while self.action_task is not None and self.agent.is_task_running(self.action_task):
                tick()
                frames += 1
                if frames > limit:
                    self.agent.cancel_task(self.action_task)
                    raise ExamError(f"arms down: pose action still running after {limit / FPS:.0f} s")
            self.action_task = None
            tick(max(0, int(round(step["duration"] * FPS)) - frames))
            return
        clip = POSE_CLIPS.get(step["pose"])
        if clip is None:
            raise ExamError(f"no pose clip for arm pose {step['pose']!r}")
        # custom_action's duration is the time in the pose AFTER the clip's blend-in (ActionStart)
        hold = float(step.get("hold_s", 0.0))
        task = self.agent.custom_action(action=clip["action"], duration=hold)
        if task == bh.BEHAVIOR_TASK_ID_INVALID:
            raise ExamError(f"{step['pose']}: custom action {clip['action']} was rejected "
                            f"(known actions: {list(self.agent.get_custom_action_names())})")
        self.action_task = task
        tick(max(1, int(round(step["duration"] * FPS))))
        status = self.agent.get_task_status(task)
        if status not in (bh.BehaviorTaskStatus.RUNNING, bh.BehaviorTaskStatus.SUCCEEDED):
            raise ExamError(f"{step['pose']}: custom action ended with {status} ({TASK_ERRORS.get(task)})")
        self.check_pose(step["pose"])

    def joint_world(self, tag):
        index = self.agent.get_joint_index(tag)
        pos, rot = carb.Float3(0, 0, 0), carb.Float4(0, 0, 0, 1)
        if index < 0 or not self.agent.get_joint_world_transform(index, pos, rot):
            return None
        return v3(pos)

    def to_body(self, v: Gf.Vec3d) -> Gf.Vec3d:
        """Stage vector -> body frame (+X left, -Y front, +Z up)."""
        front = self.facing()
        left = Gf.Vec3d(-front[1], front[0], 0.0)
        return Gf.Vec3d(Gf.Dot(v, left), -Gf.Dot(v, front), v[2])

    def check_pose(self, pose, when=""):
        """Compare each wrist with the clip's wrist offset from its anchor (library cm -> body m, scaled to this
        patient's head height); more than 12 cm off is a warning (e.g. a body much smaller/larger than the library rig)."""
        clip = POSE_CLIPS.get(pose)
        if not clip:
            return {}
        anchor_tag = LIB_TO_TAG.get(clip["anchor"], clip["anchor"])
        anchor = self.joint_world(anchor_tag)
        head = self.joint_world("Head")
        scale = (head[2] - self.position()[2]) / LIB_HEAD_M if head is not None else 1.0
        misses = {}
        for side, tag in (("left", "LeftHand"), ("right", "RightHand")):
            hand = self.joint_world(tag)
            want = clip["wrist_offsets"][side]                       # library frame cm: +X left, +Y up, +Z front
            if hand is None or anchor is None:
                continue
            want_body = Gf.Vec3d(want[0], -want[2], want[1]) * (0.01 * scale)
            got_body = self.to_body(hand - anchor)
            misses[side] = (got_body - want_body).GetLength()
            if DEBUG_HANDS:
                say(f"  debug {pose}{when} {side}: wrist - {anchor_tag} = {tuple(round(v, 3) for v in got_body)} m, "
                    f"clip {tuple(round(v, 3) for v in want_body)} m")
        if any(m > 0.12 for m in misses.values()):
            say(f"  warning: {pose}{when}: wrists {', '.join(f'{k} {v:.2f} m' for k, v in misses.items())} from the pose")
        return misses

    def release_arms(self):
        if self.action_task is not None and self.agent.is_task_running(self.action_task):
            self.agent.cancel_task(self.action_task)
        self.action_task = None


# ----------------------------------------------------------------------------------------------------------------- visits
def update_sd_info(visit: dict, status: str, error: str = None) -> None:
    path = Path(visit["sd_dir"]) / "sd_info.json"
    info = json.loads(path.read_text())
    entry = info["visits"].setdefault(f"{visit['exam']}/{visit['room']['id']}", {})
    entry.update({"status": status, "timeline": visit["timeline"], "finished": sdmod.now_iso()})
    if error:
        entry["error"] = error
    sdmod.write_json(path, info)


STEP_STATE = {"step": 0, "op": "", "projection": "", "fov": 0}     # current step, for frames.csv


class DataCapture:
    """Dataset frames of one visit: <capture dir>/<CAMERA>/RGB/<frame>.png, .../Depth/<frame>.npy|png (metric) and
    .../Depth_Preview/<frame>.png (8-bit, for viewing),
    plus <capture dir>/frames.csv (frame, simulated time, step, op, projection, FOV light on)."""

    def __init__(self, stage, visit: dict, cfg: dict, t0: float):
        import csv
        from concurrent.futures import ThreadPoolExecutor

        import omni.replicator.core as rep
        self.cfg, self.t0 = cfg, t0
        self.every_n = max(1, round(FPS / float(cfg.get("fps", FPS))))      # capture.fps -> every n-th simulated frame
        self.out = Path(visit["capture"]["dir"])
        self.streams, self.frame, self.saved, self.active = [], 0, 0, cfg.get("start", "spawn") == "spawn"
        rgb_on, depth_on = (cfg.get("streams") or {}).get("rgb", True), (cfg.get("streams") or {}).get("depth", True)
        self.depth_preview = depth_on and cfg.get("depth_preview", True)
        self.preview_range = [float(v) for v in cfg.get("depth_preview_range_m", [0.3, 8.0])]
        products = {}

        def product(path):
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsA(UsdGeom.Camera):
                raise ExamError(f"capture camera {path} not found in the room")
            res = cfg.get("resolution", "native")
            if res == "native":
                attr = prim.GetAttribute("sdg:resolution")
                res = tuple(int(v) for v in attr.Get()) if attr and attr.Get() is not None else (1280, 720)
            if path not in products:
                products[path] = (rep.create.render_product(path, tuple(res)), tuple(res))
            return products[path][0]

        for cam in visit["capture"]["cameras"]:
            base = "/World/Room/Cameras"
            if cam.get("rig"):
                rgb_path, depth_path = f"{base}/{cam['rig']}/{cam['rig']}_RGB", f"{base}/{cam['rig']}/{cam['rig']}_Depth"
            else:
                rgb_path = depth_path = f"{base}/{cam['camera']}"
            for kind, on, path, annot_name in (("RGB", rgb_on, rgb_path, "rgb"),
                                               ("Depth", depth_on, depth_path, "distance_to_image_plane")):
                if not on:
                    continue
                annot = rep.AnnotatorRegistry.get_annotator(annot_name)
                annot.attach([product(path)])
                (self.out / cam["name"] / kind).mkdir(parents=True, exist_ok=True)
                if kind == "Depth" and self.depth_preview:
                    (self.out / cam["name"] / "Depth_Preview").mkdir(parents=True, exist_ok=True)
                self.streams.append((cam["name"], kind, annot))
        for _ in range(60):                       # renderer warm-up: every stream must deliver before frame 1
            APP.update()
            if all(getattr(a.get_data(), "size", 0) for _, _, a in self.streams):
                break
        else:
            raise ExamError("capture: cameras deliver no images after 60 updates")
        self.pool = ThreadPoolExecutor(max_workers=int(cfg.get("write_threads", 6)))
        self.pending = []
        self.csv_file = open(self.out / "frames.csv", "w", newline="")
        self.csv = csv.writer(self.csv_file)
        self.csv.writerow(["frame", "time_s", "step", "op", "projection", "fov_light"])
        say(f"  capture: {len(self.streams)} streams ({', '.join(f'{n}/{k}' for n, k, _ in self.streams)}) -> {self.out}")

    def _write(self, path, kind, data):
        from PIL import Image
        if kind == "RGB":
            img = Image.fromarray(np.asarray(data)[:, :, :3])
            if self.cfg.get("rgb_format", "png") == "jpg":
                img.save(path.with_suffix(".jpg"), quality=int(self.cfg.get("jpg_quality", 95)))
            else:
                img.save(path.with_suffix(".png"))
        else:
            depth = np.asarray(data, dtype=np.float32)
            depth = np.where(np.isfinite(depth), depth, 0.0)
            if self.cfg.get("depth_format", "npy") == "png16":
                Image.fromarray(np.clip(depth * 1000.0, 0, 65535).astype(np.uint16)).save(path.with_suffix(".png"))
            else:
                np.save(path.with_suffix(".npy"), depth)
            if self.depth_preview:                # viewable 8-bit image: near = white, far = dark grey, no hit = black
                near, far = self.preview_range
                grey = 255.0 - 215.0 * np.clip((depth - near) / (far - near), 0.0, 1.0)
                grey = np.where(depth > 0, grey, 0.0).astype(np.uint8)
                Image.fromarray(grey).save(path.parent.parent / "Depth_Preview" / f"{path.name}.png")

    def on_frame(self):
        if not self.active:
            return
        self.tick_count = getattr(self, "tick_count", 0) + 1
        if (self.tick_count - 1) % self.every_n:
            return
        images = [(cam, kind, annot.get_data()) for cam, kind, annot in self.streams]
        if not all(getattr(d, "size", 0) for _, _, d in images):
            say(f"  warning: capture: a camera delivered no image at t={sim_time() - self.t0:.2f}s; frame skipped")
            return
        self.frame += 1                           # frames are numbered without gaps, identical for every camera
        name = f"{self.frame:06d}"
        for cam, kind, data in images:
            self.pending.append(self.pool.submit(self._write, self.out / cam / kind / name, kind, np.array(data)))
        self.csv.writerow([self.frame, f"{sim_time() - self.t0:.4f}", STEP_STATE["step"], STEP_STATE["op"],
                           STEP_STATE["projection"], STEP_STATE["fov"]])
        self.saved += 1
        if len(self.pending) > 64:                  # bound memory: wait for the oldest writes
            for f in self.pending[:32]:
                f.result()
            self.pending = self.pending[32:]

    def close(self):
        for f in self.pending:
            f.result()
        self.pool.shutdown(wait=True)
        self.csv_file.close()
        return self.saved


class DebugCapture:
    """Optional (isaac.debug_capture_dir): PNG frames of the visit for checking motion, poses and clothing.

    Cameras: the room's CeilingCam_FarLeft and D455 colour cameras (Left / Right / Front) plus "follow", a close camera
    that tracks the patient from the room-centre side (never inside a wall). Frames go to <dir>/<visit>/<camera>/.
    With isaac.debug_capture_every_n_frames > 0 every n-th frame of the whole visit is saved; otherwise one frame
    per pose (and per step with debug_capture_every_step)."""

    ROOM_CAMS = (("CeilingCam_FarLeft", "/World/Room/Cameras/CeilingCam_FarLeft", (640, 480)),
                 ("D455_Left", "/World/Room/Cameras/RealSense_D455_Left/RealSense_D455_Left_RGB", (400, 640)),
                 ("D455_Right", "/World/Room/Cameras/RealSense_D455_Right/RealSense_D455_Right_RGB", (400, 640)),
                 ("D455_Front", "/World/Room/Cameras/RealSense_D455_Front/RealSense_D455_Front_RGB", (400, 640)))

    def __init__(self, stage, patient, out_dir, label):
        import omni.replicator.core as rep
        self.stage, self.patient, self.rep = stage, patient, rep
        self.out = Path(out_dir) / label
        self.count = 0
        self.annotators = []
        self.step_tag = "start"
        self.every_n = int(ISAAC.get("debug_capture_every_n_frames") or 0)
        for name, focal, res in (("follow", 16.0, (640, 800)), ("close_front", 24.0, (800, 640)),
                                 ("close_back", 24.0, (800, 640))):
            cam = UsdGeom.Camera.Define(stage, f"/World/DebugCams/{name}")
            cam.CreateFocalLengthAttr(focal)
            cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 50.0))
            self._attach(name, cam.GetPath().pathString, res)
        for name, path, res in self.ROOM_CAMS:
            if stage.GetPrimAtPath(path):
                self._attach(name, path, res)
        for name, _ in self.annotators:
            (self.out / name).mkdir(parents=True, exist_ok=True)
        self._frame = 0

    def _attach(self, name, path, res):
        rp = self.rep.create.render_product(path, res)
        annot = self.rep.AnnotatorRegistry.get_annotator("rgb")
        annot.attach([rp])
        self.annotators.append((name, annot))

    def _aim(self):
        """Follow camera 1.7 m from the patient towards the room centre (stage origin), slightly to the side."""
        pos = self.patient.position()
        to_centre = Gf.Vec3d(-pos[0], -pos[1], 0.0)
        if to_centre.GetLength() < 0.3:
            to_centre = self.patient.facing()
        d = to_centre.GetNormalized()
        side = Gf.Vec3d(-d[1], d[0], 0.0)
        eye = pos + d * 1.6 + side * 0.5 + UP * 1.3
        self._place("follow", eye, pos + UP * 1.0)
        # close-ups of the upper body / hands, 1.1 m in front of and behind the patient (head height)
        front = self.patient.facing()
        head = self.patient.joint_world("Head") or (pos + UP * 1.5)
        left = Gf.Vec3d(-front[1], front[0], 0.0)
        self._place("close_front", head + front * 1.1 + left * 0.25 + UP * 0.05, head - UP * 0.15)
        self._place("close_back", head - front * 1.1 - left * 0.25 + UP * 0.05, head - UP * 0.15)

    def _place(self, name, eye, target):
        view = Gf.Matrix4d().SetLookAt(eye, target, UP).GetInverse()
        xf = UsdGeom.Xformable(self.stage.GetPrimAtPath(f"/World/DebugCams/{name}"))
        ops = xf.GetOrderedXformOps()
        (ops[0] if ops else xf.AddTransformOp()).Set(view)

    def _save(self, tag):
        from PIL import Image
        self.count += 1
        t = sim_time()
        for name, annot in self.annotators:
            data = annot.get_data()
            if data is None or getattr(data, "size", 0) == 0:
                continue
            Image.fromarray(data[:, :, :3]).save(self.out / name / f"{self.count:05d}_t{t:07.2f}_{tag}.png")

    def on_frame(self):
        """Called after every simulated frame (tick)."""
        self._frame += 1
        if self.every_n:
            self._aim()
            if self._frame % self.every_n == 0:
                self._save(self.step_tag)

    def snap(self, tag):
        if self.every_n:
            return
        self._aim()
        tick(4)                                  # let the renderer catch up (through tick: dataset frames continue)
        self._save(tag)
        say(f"  capture: {tag} -> {self.out}")


def set_viewport_camera(stage) -> None:
    """GUI: look through isaac.viewport_camera (a room camera name, default CeilingCam_FarLeft)."""
    name = ISAAC.get("viewport_camera")
    if HEADLESS or not name:
        return
    path = f"/World/Room/Cameras/{name}"
    if not stage.GetPrimAtPath(path).IsA(UsdGeom.Camera):
        say(f"  warning: viewport camera {path} not found; keeping the default view")
        return
    try:
        from omni.kit.viewport.utility import get_active_viewport
        viewport = get_active_viewport()
        if viewport is not None:
            viewport.camera_path = path
            say(f"  viewport camera: {name}")
    except Exception as exc:                       # the viewport is a convenience; never fail a visit for it
        say(f"  warning: could not set the viewport camera ({exc})")


def run_visit(visit: dict, number: int, total: int) -> None:
    human, room = visit["human"], visit["room"]
    say(f"=== Visit {number}/{total}: {visit['sd']}  human {human['id']}  room {room['id']}  exam {visit['exam']} "
        f"[{', '.join(visit['projections'])}]")
    stage, skelroot = build_stage(visit)
    for attempt in (1, 2):
        tick_count = 10 * attempt                 # the volume must reach the navigation plugin before baking
        for _ in range(tick_count):
            APP.update()
        if navmesh.start_navmesh_baking_and_wait():
            break
        if attempt == 2:
            raise ExamError("NavMesh baking failed (no walkable floor inside /World/NavMeshVolume?)")
    say("  stage: NavMesh baked")
    check_route(visit["steps"])

    carb.settings.get_settings().set("/app/player/useFixedTimeStepping", True)
    timeline.set_time_codes_per_second(FPS)
    timeline.set_start_time(0.0)
    timeline.set_end_time(1.0e6)
    timeline.set_play_every_frame(True)
    timeline.set_looping(False)
    set_viewport_camera(stage)
    timeline.play()
    tick(2)
    patient = Patient(stage, skelroot, human)
    capture = DebugCapture(stage, patient, ISAAC["debug_capture_dir"], f"{visit['sd']}_{visit['exam']}_{room['id']}") \
        if ISAAC.get("debug_capture_dir") else None
    FRAME_HOOKS.clear()
    if capture:
        FRAME_HOOKS.append(capture.on_frame)
    log = sdmod.Timeline(visit["timeline"], visit["header"])
    t0 = sim_time()
    data_cap = None
    if (JOB.get("capture") or {}).get("enabled") and visit.get("capture"):
        data_cap = DataCapture(stage, visit, JOB["capture"], t0)
        FRAME_HOOKS.append(data_cap.on_frame)
    cap_start = (JOB.get("capture") or {}).get("start", "spawn")
    try:
        for step in visit["steps"]:
            STEP_STATE.update(step=step["index"], op=step["op"], projection=step.get("projection") or "")
            if data_cap and cap_start == "detector_marker":
                data_cap.active = bool(step.get("projection")) or step.get("say") == "Model idle on the detector marker"
            if capture:
                capture.step_tag = f"s{step['index']:02d}_{step['op']}" + \
                    (f"_{step.get('projection')}" if step.get("projection") else "") + (f"_{step['pose']}" if step.get("pose") else "")
            if step.get("say"):
                line = log.event(sim_time() - t0, step["say"])
                say(f"  {visit['sd']} {line.split('  ', 1)[1]}")
            op = step["op"]
            if op == "spawn":
                patient.spawn(step)
            elif op == "idle":
                patient.idle(step)
            elif op == "walk":
                patient.walk(step)
            elif op == "turn":
                patient.turn(step)
            elif op == "arms":
                patient.arms(step)
            elif op == "fov":
                if step["on"]:
                    patient.check_pose(step.get("pose_name", ""), " at FOV on")
                set_fov_light(stage, step["on"])
                STEP_STATE["fov"] = int(step["on"])
                tick()
            else:
                raise ExamError(f"unknown step op {op!r}")
            if step.get("done"):
                line = log.event(sim_time() - t0, step["done"])
                say(f"  {visit['sd']} {line.split('  ', 1)[1]}")
            if capture and (ISAAC.get("debug_capture_every_step") or op == "arms" or (op == "fov" and step["on"]) or
                            (op == "idle" and step.get("say") == "Model idle on the detector marker")):
                capture.snap(f"s{step['index']:02d}_{step.get('projection') or step.get('target') or 'visit'}_{step.get('pose') or op}")
    except Exception as exc:
        FRAME_HOOKS.clear()
        if data_cap:
            data_cap.close()
        log.event(sim_time() - t0, f"ERROR: {exc}")
        log.close("failed")
        raise
    patient.release_arms()
    FRAME_HOOKS.clear()
    simulated = sim_time() - t0
    if data_cap:
        saved = data_cap.close()
        say(f"  capture: {saved} frames x {len(data_cap.streams)} streams written to {data_cap.out}")
    log.close("ok")
    timeline.stop()
    APP.update()
    update_sd_info(visit, "ok")
    say(f"  {visit['sd']} {visit['exam']} done: {simulated:.1f} s simulated -> {visit['timeline']}")


def main() -> int:
    visits = JOB["visits"]
    for k, visit in enumerate(visits, 1):
        try:
            run_visit(visit, k, len(visits))
        except Exception as exc:
            say(f"[ERROR] {visit['sd']} {visit['exam']} human {visit['human']['id']} room {visit['room']['id']}: {exc}")
            if not isinstance(exc, ExamError):
                traceback.print_exc()
            update_sd_info(visit, "failed", str(exc))
            return 1
    say(f"All {len(visits)} visit(s) done")
    if ISAAC.get("keep_open") and not HEADLESS:
        say("Isaac Sim stays open (keep_open); close the window to finish")
        while APP.is_running():
            APP.update()
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception as exc:     # set-up errors outside a visit
        say(f"[ERROR] {exc}")
        traceback.print_exc()
    finally:
        sys.stdout.flush()
        shutil.rmtree(CLIP_DIR, ignore_errors=True)
        APP.close()
    sys.exit(code)
