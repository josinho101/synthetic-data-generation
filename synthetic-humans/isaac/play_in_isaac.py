"""Run inside Isaac Sim (Window -> Script Editor): load animated humans, play, read landmarks per frame.

1. Generate the animated scenes (done automatically by the pipeline, or by hand):
       python isaac/animate_human.py <run>/humans/H0001/H0001.usd       # -> H0001_anim.usda
2. Edit HUMANS below (paths to *_anim.usda) and run this script in Isaac Sim's Script Editor.
   Each human is referenced under /World/Patients/<id>, placed OFFSET_M apart, and the timeline plays.
   With PRINT_LANDMARKS = True, LM_* joint world positions are printed every PRINT_EVERY frames.
"""

import omni.timeline
import omni.usd
from pxr import Gf, Usd, UsdGeom, UsdSkel

HUMANS = [
    "/path/to/output/humans/run-XXXX/humans/H0001/H0001_anim.usda",
]
OFFSET_M = 1.5               # spacing between humans along X
PRINT_LANDMARKS = True
PRINT_EVERY = 30             # frames
LANDMARKS = ["T7", "L3", "tragus_L", "C7_surf"]

stage = omni.usd.get_context().get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.Xform.Define(stage, "/World/Patients")

readers = []
end_time = 0.0
for k, path in enumerate(HUMANS):
    holder = UsdGeom.Xform.Define(stage, f"/World/Patients/P{k:03d}")
    holder.GetPrim().GetReferences().AddReference(path)          # brings /World/<id> (+ animation)
    UsdGeom.XformCommonAPI(holder).SetTranslate(Gf.Vec3d(k * OFFSET_M, 0.0, 0.0))
    layer_stage = Usd.Stage.Open(path)
    end_time = max(end_time, layer_stage.GetEndTimeCode() / layer_stage.GetTimeCodesPerSecond())
    stage.SetTimeCodesPerSecond(layer_stage.GetTimeCodesPerSecond())
    for prim in Usd.PrimRange(holder.GetPrim()):
        if prim.IsA(UsdSkel.Skeleton):
            readers.append((path, prim))

stage.SetStartTimeCode(0)
stage.SetEndTimeCode(end_time * stage.GetTimeCodesPerSecond())
timeline = omni.timeline.get_timeline_interface()
timeline.set_end_time(end_time)
timeline.set_looping(True)
timeline.play()

if PRINT_LANDMARKS:
    cache = UsdSkel.Cache()
    queries = [(path, prim, cache.GetSkelQuery(UsdSkel.Skeleton(prim))) for path, prim in readers]
    state = {"frame": 0}

    def _on_update(event):
        state["frame"] += 1
        if state["frame"] % PRINT_EVERY:
            return
        time = Usd.TimeCode(timeline.get_current_time() * stage.GetTimeCodesPerSecond())
        for path, prim, query in queries:
            joints = list(query.GetJointOrder())
            skel_xf = query.ComputeJointSkelTransforms(time)
            to_world = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(time)
            values = {}
            for j, xf in zip(joints, skel_xf):
                leaf = j.split("/")[-1]
                if leaf.startswith("LM_") and leaf[3:] in LANDMARKS:
                    values[leaf[3:]] = tuple(round(v, 3) for v in (xf * to_world).ExtractTranslation())
            print(f"t={time.GetValue():6.0f} {prim.GetPath()} {values}")

    import omni.kit.app
    _subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(_on_update)
