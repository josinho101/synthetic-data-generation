"""X-ray arm poses as behavior-system custom actions (pxr only: usd-core or Isaac's Python).

The behavior system plays motion clips authored on its motion library skeleton (NVIDIA "Human" rig: 81 joints,
Y up, +Z front, +X = the character's left, cm) and retargets them at run time onto each agent. `reach_hand` (whole-body
reach IK) cannot hold an X-ray posture: the torso leans and twists. Instead, each arm pose of poses.yaml becomes a
small clip built from the library's own standing idle:

  frames [0, in)          blend from the idle into the pose      annotation ActionStart (track 3)
  frames [in, in+loop)    hold the pose; legs/torso keep idling  annotation ActionLoop  (track 2)
  frames [in+loop, end]   blend back to the idle                 annotation ActionEnd   (track 4)
  + the action-name annotation (track 1), BehaviorActionAPI (behavior:action:name), AnimationSkelBindingAPI.

The posed arm joints come from a two-bone IK on the library skeleton: wrist at `anchor joint + wrist_cm`, elbow bent
towards `elbow`, hand oriented by `fingers` (wrist -> middle finger) and `palm` (palm normal). Right arms mirror the
left spec (X negated) unless `right` is given. An optional `via` (same fields) is an intermediate arm pose the blend
passes through halfway in and out (e.g. arms out to the sides, elbows bent, before the hands go onto the head);
every joint blends along the shorter rotation arc, so both arms move as mirror images.
"""

import math

from pxr import Gf, Sdf, Usd, UsdSkel, Vt

ARM = {"left": ("L_Clavicle", "L_UpArm", "L_LoArm", "L_Wrist", "L_MiddleFinger1", "L_IndexFinger1", "L_PinkyFinger1"),
       "right": ("R_Clavicle", "R_UpArm", "R_LoArm", "R_Wrist", "R_MiddleFinger1", "R_IndexFinger1", "R_PinkyFinger1")}


class ClipError(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------------------------- math
def _local_matrix(rotation, translation) -> Gf.Matrix4d:
    m = Gf.Matrix4d(1.0)
    m.SetRotateOnly(Gf.Quatd(rotation))
    m.SetTranslateOnly(Gf.Vec3d(translation))
    return m


def _fk(local, parents):
    world = [None] * len(local)
    for i, parent in enumerate(parents):
        world[i] = local[i] * world[parent] if parent >= 0 else Gf.Matrix4d(local[i])
    return world


def _rotation_about(matrix: Gf.Matrix4d, rotation: Gf.Matrix3d, pivot: Gf.Vec3d) -> Gf.Matrix4d:
    """World matrix rotated by `rotation` (row-vector convention) about `pivot`."""
    r = Gf.Matrix4d(1.0)
    r.SetRotateOnly(rotation)
    return matrix * Gf.Matrix4d(1.0).SetTranslate(-pivot) * r * Gf.Matrix4d(1.0).SetTranslate(pivot)


def _frame(primary: Gf.Vec3d, secondary: Gf.Vec3d) -> Gf.Matrix3d:
    """Orthonormal frame (rows): x = primary, y = secondary made perpendicular, z = x cross y."""
    x = primary.GetNormalized()
    y = secondary - x * Gf.Dot(secondary, x)
    if y.GetLength() < 1e-8:
        y = Gf.Vec3d(0, 1, 0) - x * x[1]
        if y.GetLength() < 1e-8:
            y = Gf.Vec3d(0, 0, 1) - x * x[2]
    y = y.GetNormalized()
    z = Gf.Cross(x, y)
    return Gf.Matrix3d(x[0], x[1], x[2], y[0], y[1], y[2], z[0], z[1], z[2])


def _align(cur_primary, cur_secondary, new_primary, new_secondary) -> Gf.Matrix3d:
    """Rotation (row vectors) taking the current (primary, secondary) frame onto the new one."""
    return _frame(cur_primary, cur_secondary).GetTranspose() * _frame(new_primary, new_secondary)


def _minimal(cur: Gf.Vec3d, new: Gf.Vec3d) -> Gf.Matrix3d:
    return Gf.Matrix3d(1.0).SetRotate(Gf.Rotation(cur, new))


# ----------------------------------------------------------------------------------------------------------- IK
def _mirror(spec: dict) -> dict:
    out = {}
    for key, value in spec.items():
        out[key] = [-value[0], value[1], value[2]] if isinstance(value, (list, tuple)) and len(value) == 3 else value
    return out


def _idle_elbow_hinges(index, parents, local) -> dict:
    """{side: elbow hinge (bend-plane normal, world)} of the idle arms, both taken from the arm with the larger bend.

    The library's idle bends one elbow ~15 deg and leaves the other almost straight (~4 deg): the straight arm's
    bend plane is noise (it pointed forward instead of sideways) and gave that upper arm a ~90 deg wrong twist,
    which wrung the shoulder skin. The other arm uses the mirror image (X negated; the cross product of mirrored
    vectors flips sign), so both arms get mirror-image twists."""
    world = _fk(local, parents)
    normals = {}
    for side in ("left", "right"):
        up, lo, wrist = (index[n] for n in ARM[side][1:4])
        s, e, w = (world[i].ExtractTranslation() for i in (up, lo, wrist))
        normals[side] = Gf.Cross(e - s, w - e)
    ref = max(normals, key=lambda k: normals[k].GetLength())
    if normals[ref].GetLength() < 1e-6:
        raise ClipError("both idle elbows are straight: the elbow hinge axis is undefined")
    n = normals[ref].GetNormalized()
    other = "right" if ref == "left" else "left"
    return {ref: n, other: Gf.Vec3d(n[0], -n[1], -n[2])}


def posed_arm_locals(joints, parents, base_local, pose: dict) -> dict:
    """{joint index: local matrix} of the arm joints for one arm pose, solved on the base (idle frame) pose."""
    index = {j.split("/")[-1]: i for i, j in enumerate(joints)}
    anchor = pose.get("anchor", "Head")
    if anchor not in index:
        raise ClipError(f"anchor joint {anchor!r} not in the motion library skeleton")
    local = [Gf.Matrix4d(m) for m in base_local]
    hinges = _idle_elbow_hinges(index, parents, local)
    for side in ("left", "right"):
        spec = pose.get(side) or (_mirror(pose["left"]) if side == "right" and "left" in pose else None)
        if not spec:
            continue
        clav, up, lo, wrist, middle, idx_f, pinky = (index[n] for n in ARM[side])
        world = _fk(local, parents)
        s, e, w = (world[i].ExtractTranslation() for i in (up, lo, wrist))
        target = world[index[anchor]].ExtractTranslation() + Gf.Vec3d(*spec["wrist_cm"])
        a, b = (e - s).GetLength(), (w - e).GetLength()
        to_t = target - s
        d = min(max(to_t.GetLength(), abs(a - b) + 1e-3), a + b - 1e-3)
        u = to_t.GetNormalized()
        pole = Gf.Vec3d(*spec.get("elbow", [1, 0, -1] if side == "left" else [-1, 0, -1]))
        n = pole - u * Gf.Dot(pole, u)
        if n.GetLength() < 1e-6:
            raise ClipError(f"{side} arm: elbow direction is parallel to the shoulder->wrist line")
        n = n.GetNormalized()
        cos_a = (a * a + d * d - b * b) / (2 * a * d)
        sin_a = math.sqrt(max(0.0, 1 - cos_a * cos_a))
        e_new = s + u * (a * cos_a) + n * (a * sin_a)
        w_new = s + u * d
        # upper arm: bone direction + bend plane (the idle elbow hinge, mirrored from the better-bent arm)
        cur_plane = hinges[side]
        new_plane = Gf.Cross(e_new - s, w_new - e_new)
        rot = _align(e - s, cur_plane, e_new - s, new_plane)
        local[up] = _rotation_about(world[up], rot, s) * world[parents[up]].GetInverse()
        # forearm: straight onto the solved wrist
        world = _fk(local, parents)
        e2, w2 = world[lo].ExtractTranslation(), world[wrist].ExtractTranslation()
        local[lo] = _rotation_about(world[lo], _minimal(w2 - e2, w_new - e2), e2) * world[parents[lo]].GetInverse()
        # hand: fingers direction + palm normal; the palm's turn (pronation / supination) is shared between the
        # forearm roll and the wrist like in a real arm, so neither joint wrings the skin (candy-wrapper wrist)
        fingers_new = Gf.Vec3d(*spec.get("fingers", [0, -1, 0]))
        palm_new = Gf.Vec3d(*spec.get("palm", [0, 0, 1]))
        world = _fk(local, parents)
        e3 = world[lo].ExtractTranslation()
        axis = (world[wrist].ExtractTranslation() - e3).GetNormalized()
        lo_unrolled = Gf.Matrix4d(local[lo])

        def hand_local(roll_deg):
            local[lo] = lo_unrolled
            w0 = _fk(local, parents)
            if roll_deg:
                local[lo] = _rotation_about(w0[lo], Gf.Matrix3d(1.0).SetRotate(Gf.Rotation(axis, roll_deg)), e3) * \
                    w0[parents[lo]].GetInverse()
            w1 = _fk(local, parents)
            p = w1[wrist].ExtractTranslation()
            fingers_cur = w1[middle].ExtractTranslation() - p
            across = w1[idx_f].ExtractTranslation() - w1[pinky].ExtractTranslation()
            palm_cur = Gf.Cross(fingers_cur, across) if side == "left" else Gf.Cross(across, fingers_cur)
            return _rotation_about(w1[wrist], _align(fingers_cur, palm_cur, fingers_new, palm_new), p) * \
                w1[parents[wrist]].GetInverse()

        def wrist_turn(m):              # how far the wrist turns away from its idle local rotation (deg)
            q = (Gf.Matrix4d(base_local[wrist]).ExtractRotationQuat().GetInverse() * m.ExtractRotationQuat())
            return math.degrees(2 * math.acos(min(1.0, abs(q.GetReal()))))

        best = min(range(-180, 181, 5), key=lambda r: wrist_turn(hand_local(r)))
        roll = float(spec.get("forearm_roll_share", 0.6)) * best
        local[wrist] = hand_local(roll)
        local[wrist] = hand_local(roll)          # (re-evaluated so local[lo] holds this roll)
    arm_joints = {index[n] for side in ("left", "right") for n in ARM[side][1:4]}
    return {i: local[i] for i in arm_joints}


def wrist_positions(joints, parents, local) -> dict:
    index = {j.split("/")[-1]: i for i, j in enumerate(joints)}
    world = _fk(local, parents)
    return {name: world[index[name]].ExtractTranslation() for name in ("L_Wrist", "R_Wrist", "Head", "Pelvis")}


# ----------------------------------------------------------------------------------------------------------- clip
def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _slerp_short(w: float, a: Gf.Quatf, b: Gf.Quatf) -> Gf.Quatf:
    """Slerp along the shorter arc (q and -q are the same rotation; without this one arm may swing the long way)."""
    if Gf.Dot(a, b) < 0:
        b = -b
    return Gf.Slerp(w, a, b).GetNormalized()


def _blend_arm(idle: Gf.Quatf, via, posed: Gf.Quatf, p: float) -> Gf.Quatf:
    """Arm joint rotation at progress p (0 idle -> 1 posed), through the via pose at p = 0.5 when given."""
    if via is None:
        return _slerp_short(_smooth(p), idle, posed)
    if p < 0.5:
        return _slerp_short(_smooth(p / 0.5), idle, via)
    return _slerp_short(_smooth((p - 0.5) / 0.5), via, posed)


def read_idle(anim: UsdSkel.Animation):
    """(joints, [(rotations, translations) per frame]) of the library's Idle clip."""
    joints = list(anim.GetJointsAttr().Get())
    times = sorted(anim.GetRotationsAttr().GetTimeSamples()) or [Usd.TimeCode.Default()]
    frames = [(list(anim.GetRotationsAttr().Get(t)), list(anim.GetTranslationsAttr().Get(t))) for t in times]
    return joints, frames


def write_pose_clip(path: str, action_name: str, joints, idle_frames, pose: dict, fps: float = 30.0,
                    blend_in_s: float = 1.2, hold_s: float = 2.0, blend_out_s: float = 1.0) -> dict:
    """Write the custom-action clip for one arm pose. Returns frame ranges and the posed wrist positions (cm)."""
    parents = list(UsdSkel.Topology(joints).GetParentIndices())
    rot0, tr0 = idle_frames[0]
    base = [_local_matrix(r, t) for r, t in zip(rot0, tr0)]
    posed = posed_arm_locals(joints, parents, base, pose)
    posed_q = {i: Gf.Quatf(m.ExtractRotationQuat()) for i, m in posed.items()}
    via_q = None
    if pose.get("via"):        # intermediate arm pose on the way in and out (e.g. elbows out, hands up)
        via_pose = {"anchor": pose.get("anchor", "Head"), "left": pose["via"]}
        if pose.get("via_right"):
            via_pose["right"] = pose["via_right"]
        via_q = {i: Gf.Quatf(m.ExtractRotationQuat()) for i, m in posed_arm_locals(joints, parents, base, via_pose).items()}
    n_in, n_hold, n_out = (max(1, int(round(s * fps))) for s in (blend_in_s, hold_s, blend_out_s))
    total = n_in + n_hold + n_out

    layer = Sdf.Layer.CreateNew(path) if not Sdf.Layer.FindOrOpen(path) else Sdf.Layer.FindOrOpen(path)
    layer.Clear()
    stage = Usd.Stage.Open(layer)
    stage.SetMetadata("upAxis", "Y")
    stage.SetMetadata("metersPerUnit", 0.01)
    stage.SetTimeCodesPerSecond(fps)
    stage.SetFramesPerSecond(fps)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(total)
    anim = UsdSkel.Animation.Define(stage, "/Root")
    stage.SetDefaultPrim(anim.GetPrim())
    anim.CreateJointsAttr(Vt.TokenArray(joints))
    anim.CreateScalesAttr(Vt.Vec3hArray([Gf.Vec3h(1, 1, 1)] * len(joints)))
    rot_attr, tr_attr = anim.CreateRotationsAttr(), anim.CreateTranslationsAttr()
    for f in range(total + 1):
        rot, tr = idle_frames[f % len(idle_frames)]
        # progress p: 0 = idle, 1 = posed (rises over the blend-in, falls over the blend-out)
        p = f / n_in if f < n_in else (1.0 if f < n_in + n_hold else 1.0 - (f - n_in - n_hold) / n_out)
        rotations = [Gf.Quatf(q) for q in rot]
        for i, q in posed_q.items():
            rotations[i] = _blend_arm(Gf.Quatf(rot[i]), via_q.get(i) if via_q else None, q, p)
        rot_attr.Set(Vt.QuatfArray(rotations), f)
        tr_attr.Set(Vt.Vec3fArray([Gf.Vec3f(t) for t in tr]), f)
    prim = anim.GetPrim()
    prim.AddAppliedSchema("AnimationSkelBindingAPI")
    prim.AddAppliedSchema("BehaviorActionAPI")
    prim.CreateAttribute("behavior:action:name", Sdf.ValueTypeNames.String).Set(action_name)

    def annotation(name, tag, start, end, track):
        a = stage.DefinePrim(f"/Root/{name}", "SkelAnimationAnnotation")
        a.CreateAttribute("tag", Sdf.ValueTypeNames.String).Set(tag)
        a.CreateAttribute("start", Sdf.ValueTypeNames.Double).Set(float(start))
        a.CreateAttribute("end", Sdf.ValueTypeNames.Double).Set(float(end))
        a.CreateAttribute("track", Sdf.ValueTypeNames.Int).Set(track)

    annotation(action_name, action_name, 0, total, 1)
    annotation("ActionStart", "ActionStart", 0, n_in, 3)
    annotation("ActionLoop", "ActionLoop", n_in, n_in + n_hold, 2)
    annotation("ActionEnd", "ActionEnd", n_in + n_hold, total, 4)
    layer.Save()
    posed_local = list(base)
    for i, m in posed.items():
        posed_local[i] = m
    return {"frames": total, "start": [0, n_in], "loop": [n_in, n_in + n_hold], "end": [n_in + n_hold, total],
            "posed": {k: [round(v, 1) for v in p] for k, p in wrist_positions(joints, parents, posed_local).items()}}
