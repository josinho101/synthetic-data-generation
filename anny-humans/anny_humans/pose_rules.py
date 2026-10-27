"""Rig-independent X-ray exam posing, coupled anatomical motion and range-of-motion checks (numpy only).

Shared verbatim by the MPFB (mpfb-humans) and MHR (mhr-synthetic-human) pipelines. The rig is
described by configs/poses.yaml -> rig (joint names per role); everything else uses the shared
LM_ / AN_ joints, so both rigs are posed, driven and measured by the same rules.

Matrices are 4x4, column-vector convention (world = parent_world @ local). Skeleton space:
metres, Z-up, anterior = -Y, subject's left = +X.

    Poser(skel, rig_cfg).apply(EXAM_POSES[name])   -> local transforms of one pose
    angles(poser) / validate(angles, ROM)          -> clinical joint angles and ROM violations
"""

import math

import numpy as np

ANTERIOR, SUPERIOR, RIGHT = np.array([0.0, -1.0, 0.0]), np.array([0.0, 0.0, 1.0]), np.array([-1.0, 0.0, 0.0])
SIDES = ("L", "R")

# Normal adult active range of motion (deg, AAOS-style). Negative = the opposite motion
# (extension, adduction, supination, plantarflexion, bend / rotation to the left).
ROM = {
    "trunk_flexion": (-25, 80), "trunk_lateral": (-35, 35), "trunk_rotation": (-45, 45),
    "neck_flexion": (-60, 50), "neck_lateral": (-45, 45), "neck_rotation": (-80, 80),
    "shoulder_elevation": (0, 180), "shoulder_extension": (0, 60),
    "elbow_flexion": (-10, 150), "forearm_pronation": (-80, 80),
    "hip_flexion": (-30, 120), "hip_abduction": (-30, 45), "knee_flexion": (-10, 135),
    "ankle_dorsiflexion": (-50, 20),
}

# Exam poses (same anatomical description for every rig). Arm offsets are (lateral, anterior, up)
# in metres x stature/1.70; "dir" arms point the whole arm, "target" arms put the wrist on a landmark.
# "pronation" and "elbow_flexion_L" are absolute targets (deg), "knee_flexion_L" is relative to standing.
EXAM_POSES = {
    "neutral": {"arms": {"dir": (0.14, 0.0, -1.0), "reach": 0.985, "pole": (0.0, -1.0, 0.0)}},
    "chest_pa": {"arms": {"target": "iliac_crest_{side}", "offset": (0.035, -0.035, 0.0), "pole": (1.0, -0.6, 0.0),
                          "pronation": 75.0},
                 "clavicle_protraction": 12.0, "neck_flexion": -10.0, "breath": 1.0},
    "chest_lateral": {"arms": {"target": "vertex", "offset": (-0.05, 0.0, 0.10), "pole": (1.0, 0.3, 0.5)},
                      "breath": 1.0},
    "spine_ap": {"arms": {"dir": (0.36, 0.0, -1.0), "reach": 0.985, "pole": (0.0, -1.0, 0.0)}},
    "spine_lateral": {"arms": {"dir": (0.10, 1.0, -0.05), "reach": 0.95, "pole": (0.0, 0.0, -1.0)}},
    "trunk_flexion_30": {"arms": {"dir": (0.14, 0.0, -1.0), "reach": 0.985, "pole": (0.0, -1.0, 0.0)},
                         "trunk_flexion": 30.0, "neck_flexion": 10.0},
    "invalid_test": {"arms": {"dir": (0.14, 0.0, -1.0), "reach": 0.985, "pole": (0.0, -1.0, 0.0)},
                     "elbow_flexion_L": -25.0, "knee_flexion_L": -20.0},
}
BREATH_DEG = (8, 8, 8, 7, 7, 7, 6, 6, 6, 5, 4, 4)                     # rib elevation at full inspiration
# frames that follow a vertebral level instead of their own position in the spine distribution
DRIVE_ANCHOR = {"AN_thorax": "LM_T7", "AN_manubrium": "LM_T2", "AN_sternum_body": "LM_T5",
                "AN_xiphoid_process": "LM_T9"}


# --- small linear algebra ----------------------------------------------------------------

def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def rot(axis, deg):
    x, y, z = _unit(axis)
    a = math.radians(deg)
    c, s, t = math.cos(a), math.sin(a), 1 - math.cos(a)
    return np.array([[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                     [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                     [t * x * z - s * y, t * y * z + s * x, t * z * z + c]])


def about(R, pivot):
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = pivot - R @ pivot
    return M


def arc(a, b):
    """Shortest rotation taking direction a to direction b."""
    a, b = _unit(a), _unit(b)
    axis = np.cross(a, b)
    s, c = np.linalg.norm(axis), float(np.clip(a @ b, -1, 1))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        perp = np.cross(a, [1, 0, 0]) if abs(a[0]) < 0.9 else np.cross(a, [0, 1, 0])
        return rot(perp, 180.0)
    return rot(axis, math.degrees(math.atan2(s, c)))


def quat(R):
    w = math.sqrt(max(0.0, 1 + R[0, 0] + R[1, 1] + R[2, 2])) / 2
    x = math.copysign(math.sqrt(max(0.0, 1 + R[0, 0] - R[1, 1] - R[2, 2])) / 2, R[2, 1] - R[1, 2])
    y = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] + R[1, 1] - R[2, 2])) / 2, R[0, 2] - R[2, 0])
    z = math.copysign(math.sqrt(max(0.0, 1 - R[0, 0] - R[1, 1] + R[2, 2])) / 2, R[1, 0] - R[0, 1])
    return np.array([w, x, y, z])


def quat_mat(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def slerp(Ra, Rb, t):
    qa, qb = quat(Ra), quat(Rb)
    if qa @ qb < 0:
        qb = -qb
    d = float(np.clip(qa @ qb, -1, 1))
    if d > 0.9995:
        return quat_mat(qa + t * (qb - qa))
    th = math.acos(d)
    return quat_mat((math.sin((1 - t) * th) * qa + math.sin(t * th) * qb) / math.sin(th))


# --- skeleton ----------------------------------------------------------------------------

class Skeleton:
    def __init__(self, names, parents, rest_local):
        self.names, self.parents = list(names), list(parents)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.rest_local = np.array(rest_local, dtype=np.float64)
        self.rest_world = self.fk(self.rest_local)

    def fk(self, local):
        world = np.empty_like(local)
        for i, p in enumerate(self.parents):                       # parents precede children (UsdSkel order)
            world[i] = local[i] if p < 0 else world[p] @ local[i]
        return world


def expand_rig(rig: dict, side_tokens: dict) -> dict:
    """'{side}' in joint names -> per side {L: ..., R: ...} using the rig's side tokens."""
    def sub(value, side):
        if isinstance(value, str):
            return value.replace("{side}", side_tokens[side])
        if isinstance(value, (list, tuple)):
            return [sub(v, side) for v in value]
        return value
    out = {}
    for key, value in rig.items():
        text = repr(value)
        out[key] = {s: sub(value, s) for s in SIDES} if "{side}" in text else value
    return out


# --- clinical angles ---------------------------------------------------------------------

def _signed(a, b, axis):
    return math.degrees(math.atan2(np.cross(a, b) @ _unit(axis), a @ b))


def angles(world, skel: Skeleton) -> dict:
    """Clinical angles from the posed LM_ / AN_ joints (deg)."""
    W = lambda n: world[skel.index[n]]                              # noqa: E731
    P = lambda n: W(n)[:3, 3]                                       # noqa: E731
    out = {}

    def rel(child, parent, key):
        c, p = W(child)[:3, :3], W(parent)[:3, :3]
        y, x = c[:, 1], c[:, 0]
        out[f"{key}_flexion"] = math.degrees(math.atan2(y @ p[:, 0], y @ p[:, 1]))
        out[f"{key}_lateral"] = math.degrees(math.atan2(y @ p[:, 2], y @ p[:, 1]))
        out[f"{key}_rotation"] = math.degrees(math.atan2(-(x @ p[:, 2]), x @ p[:, 0]))

    rel("AN_thorax", "AN_pelvis", "trunk")
    rel("AN_skull", "AN_thorax", "neck")
    thorax, pelvis = W("AN_thorax")[:3, :3], W("AN_pelvis")[:3, :3]
    for s in SIDES:
        lat_t = -thorax[:, 2] if s == "L" else thorax[:, 2]
        lat_p = -pelvis[:, 2] if s == "L" else pelvis[:, 2]
        to_right = 1.0 if s == "R" else -1.0
        h = P(f"LM_elbow_centre_{s}") - P(f"LM_shoulder_centre_{s}")
        f = P(f"LM_wrist_centre_{s}") - P(f"LM_elbow_centre_{s}")
        down = -thorax[:, 1]
        out[f"shoulder_elevation_{s}"] = math.degrees(math.acos(np.clip(_unit(h) @ down, -1, 1)))
        # plane of elevation: 0 = abduction (coronal), 90 = forward flexion, < 0 = behind the body
        out[f"shoulder_plane_{s}"] = math.degrees(math.atan2(h @ thorax[:, 0], h @ lat_t))
        behind = -(h @ thorax[:, 0])
        out[f"shoulder_extension_{s}"] = (math.degrees(math.atan2(behind, h @ down))
                                         if behind > 0 and h @ down > 0 else 0.0)
        hinge = (P(f"LM_lateral_epicondyle_{s}") - P(f"LM_medial_epicondyle_{s}")) * to_right
        out[f"elbow_flexion_{s}"] = _signed(h, f, hinge)
        e = P(f"LM_lateral_epicondyle_{s}") - P(f"LM_medial_epicondyle_{s}")
        st = P(f"LM_radial_styloid_{s}") - P(f"LM_ulnar_styloid_{s}")
        a = _unit(f)
        e, st = e - (e @ a) * a, st - (st @ a) * a
        # signed angle from the epicondyle line to the styloid line about the distal forearm axis:
        # 0 = full supination (anatomical position), 90 = neutral (thumb forward), 180 = full pronation
        theta = _signed(e, st, a) * (1.0 if s == "L" else -1.0)
        out[f"forearm_pronation_{s}"] = (theta - 90.0 + 180.0) % 360.0 - 180.0
        fem = P(f"LM_knee_centre_{s}") - P(f"LM_hip_centre_{s}")
        shank = P(f"LM_ankle_centre_{s}") - P(f"LM_knee_centre_{s}")
        out[f"hip_flexion_{s}"] = math.degrees(math.atan2(fem @ pelvis[:, 0], -(fem @ pelvis[:, 1])))
        out[f"hip_abduction_{s}"] = math.degrees(math.atan2(fem @ lat_p, -(fem @ pelvis[:, 1])))
        knee_axis = (P(f"LM_lateral_femoral_epicondyle_{s}") - P(f"LM_medial_femoral_epicondyle_{s}")) * to_right
        out[f"knee_flexion_{s}"] = -_signed(fem, shank, knee_axis)
        foot = (P(f"LM_metatarsal_head_1_{s}") + P(f"LM_metatarsal_head_5_{s}")) / 2 - P(f"LM_heel_{s}")
        out[f"ankle_shank_foot_{s}"] = math.degrees(math.acos(np.clip(_unit(-shank) @ _unit(foot), -1, 1)))
    return out


# Standing rest pose = anatomical neutral for these (the rule-based joint centres are not exactly collinear)
RELATIVE_TO_REST = ("trunk_", "neck_", "ankle_shank_foot", "hip_", "knee_")


def clinical(posed: dict, rest: dict) -> dict:
    """Make trunk / neck / ankle angles relative to the standing rest pose (anatomical neutral)."""
    out = {}
    for k, v in posed.items():
        if k.startswith("ankle_shank_foot"):
            out[k.replace("ankle_shank_foot", "ankle_dorsiflexion")] = rest[k] - v
        elif k.startswith(RELATIVE_TO_REST):
            out[k] = v - rest[k]
        else:
            out[k] = v
    return {k: round(v, 2) for k, v in out.items()}


def validate(clin: dict, rom: dict = None) -> list:
    rom = rom or ROM
    bad = []
    for k, v in clin.items():
        base = k[:-2] if k[-2:] in ("_L", "_R") else k
        if base in rom and not rom[base][0] <= v <= rom[base][1]:
            bad.append({"angle": k, "value": v, "range": list(rom[base])})
    return bad


# --- posing ------------------------------------------------------------------------------

class Poser:
    def __init__(self, skel: Skeleton, rig: dict, stature: float):
        self.s, self.rig, self.k = skel, rig, stature / 1.70
        self.local = skel.rest_local.copy()
        self.world = skel.rest_world.copy()
        self.stats = {}

    def i(self, name):
        return self.s.index[name]

    def P(self, name):
        return self.world[self.i(name)][:3, 3]

    def refresh(self):
        self.world = self.s.fk(self.local)

    def rotate(self, joint, R, pivot=None):
        i = self.i(joint)
        p = self.s.parents[i]
        pivot = self.world[i][:3, 3] if pivot is None else pivot
        parent = self.world[p] if p >= 0 else np.eye(4)
        self.local[i] = np.linalg.inv(parent) @ about(R, pivot) @ self.world[i]
        self.refresh()

    def probe(self, apply, metric, want_increase=True):
        """apply(sign) rotates; keep +1 if the metric moves the wanted way, else redo with -1."""
        saved = self.local.copy()
        before = metric()
        apply(1.0)
        if (metric() > before) != want_increase:
            self.local = saved
            self.refresh()
            apply(-1.0)

    def twist(self, chain, axis, deg, pivot):
        for joint, frac in chain:
            if joint in self.s.index:
                self.rotate(joint, rot(axis, deg * frac), pivot)

    def angle(self, key):
        return angles(self.world, self.s)[key]

    # anatomical operations ----------------------------------------------------------------
    def bend_chain(self, chain, frame_col, deg, key):
        axis = self.world[self.i("AN_pelvis")][:3, frame_col]
        n = len(chain)
        self.probe(lambda sg: [self.rotate(j, rot(axis, sg * deg / n)) for j in chain],
                   lambda: self.angle(key), deg > 0)

    def clavicle_protraction(self, side, deg):
        clav = self.rig["clavicle"][side]
        axis = self.world[self.i("AN_thorax")][:3, 1]
        self.probe(lambda sg: self.rotate(clav, rot(axis, sg * deg)), lambda: -self.P(f"LM_acromion_{side}")[1])

    def arm(self, side, spec):
        r = self.rig
        hum, elb, wri = r["humerus"][side], r["elbow"][side], r["wrist"][side]
        lat = np.array([1.0 if side == "L" else -1.0, 0.0, 0.0])
        local = lambda v: v[0] * lat + v[1] * ANTERIOR + v[2] * SUPERIOR        # noqa: E731
        S, E, Wr = self.P(hum), self.P(elb), self.P(wri)
        a, b = np.linalg.norm(E - S), np.linalg.norm(Wr - E)
        if "target" in spec:
            T = self.P("LM_" + spec["target"].replace("{side}", side)) + local(spec["offset"]) * self.k
        else:
            T = S + _unit(local(spec["dir"])) * (a + b) * spec["reach"]
        u = T - S
        c = float(np.clip(np.linalg.norm(u), abs(a - b) + 1e-4, a + b - 1e-4))
        u = _unit(u)
        T = S + u * c
        pole = local(spec["pole"])
        v = _unit(pole - (pole @ u) * u)
        ca = (a * a + c * c - b * b) / (2 * a * c)
        E2 = S + a * (ca * u + math.sqrt(max(0.0, 1 - ca * ca)) * v)
        self.rotate(hum, arc(E - S, E2 - S))
        # humeral twist so the elbow hinge (epicondyle axis) is normal to the arm plane, flexing forwards
        normal = _unit(np.cross(E2 - S, T - E2))
        axis_h = _unit(E2 - S)
        best = None
        saved = self.local.copy()
        for target_n in (normal, -normal):
            self.local = saved.copy()
            self.refresh()
            e = self.P(f"LM_lateral_epicondyle_{side}") - self.P(f"LM_medial_epicondyle_{side}")
            e = _unit(e - (e @ axis_h) * axis_h)
            tau = math.degrees(math.atan2(np.cross(e, target_n) @ axis_h, e @ target_n))
            self.twist(r["humerus_twist"][side], axis_h, tau, S)
            self.rotate(elb, arc(self.P(wri) - self.P(elb), T - self.P(elb)))
            flex = self.angle(f"elbow_flexion_{side}")
            score = (flex >= -5.0, -np.linalg.norm(self.P(wri) - T))      # physiological flexion first, then reach
            if best is None or score > best[0]:
                best = (score, self.local.copy())
        self.local = best[1]
        self.refresh()
        self.stats[f"arm_reach_error_mm_{side}"] = round(float(np.linalg.norm(self.P(wri) - T) * 1000), 1)
        if spec.get("pronation") is not None:
            key = f"forearm_pronation_{side}"
            deg = spec["pronation"] - self.angle(key)
            ax = _unit(self.P(wri) - self.P(elb))
            self.probe(lambda sg: self.twist(r["forearm_twist"][side], ax, sg * abs(deg), self.P(elb)),
                       lambda: self.angle(key), deg > 0)

    def hinge(self, side, joint_role, epi, target, key, rest_relative=False):
        """Rotate a hinge joint about its epicondyle axis until the clinical angle reaches the target."""
        lat, med = (f"LM_lateral_{epi}_{side}", f"LM_medial_{epi}_{side}")
        axis = self.P(lat) - self.P(med)
        j = self.rig[joint_role][side]
        base = angles(self.s.rest_world, self.s)[key] if rest_relative else 0.0
        deg = target - (self.angle(key) - base)
        self.probe(lambda sg: self.rotate(j, rot(axis, sg * abs(deg))), lambda: self.angle(key), deg > 0)

    def apply(self, spec: dict):
        if spec.get("trunk_flexion"):
            self.bend_chain(self.rig["spine_chain"], 2, spec["trunk_flexion"], "trunk_flexion")
        if spec.get("neck_flexion"):
            self.bend_chain(self.rig["neck_chain"], 2, spec["neck_flexion"], "neck_flexion")
        for side in SIDES:
            if spec.get("clavicle_protraction"):
                self.clavicle_protraction(side, spec["clavicle_protraction"])
            if spec.get("arms"):
                self.arm(side, spec["arms"])
            if spec.get(f"elbow_flexion_{side}") is not None:
                self.hinge(side, "elbow", "epicondyle", spec[f"elbow_flexion_{side}"], f"elbow_flexion_{side}")
            if spec.get(f"knee_flexion_{side}") is not None:
                self.hinge(side, "knee", "femoral_epicondyle", spec[f"knee_flexion_{side}"], f"knee_flexion_{side}",
                           rest_relative=True)
        self.screw_home()
        self.lock()

    # coupled / anatomical constraints -------------------------------------------------------
    def screw_home(self, max_deg=6.0, range_deg=20.0):
        """Tibial internal rotation while the knee leaves full extension (screw-home mechanism)."""
        for side in SIDES:
            flex = self.angle(f"knee_flexion_{side}") - angles(self.s.rest_world, self.s)[f"knee_flexion_{side}"]
            deg = max_deg * float(np.clip(flex / range_deg, 0, 1))
            if deg < 0.5:
                continue
            knee = self.rig["knee"][side]
            axis = self.P(f"LM_knee_centre_{side}") - self.P(f"LM_ankle_centre_{side}")
            medial = np.array([-1.0 if side == "L" else 1.0, 0, 0])

            def toe_medial():
                f = (self.P(f"LM_metatarsal_head_1_{side}") + self.P(f"LM_metatarsal_head_5_{side}")) / 2
                return _unit(f - self.P(f"LM_heel_{side}")) @ medial
            self.probe(lambda sg: self.twist(self.rig["shank_twist"][side], axis, sg * deg, self.P(knee)), toe_medial)
            self.stats[f"screw_home_deg_{side}"] = round(deg, 2)

    def lock(self):
        """Joints that do not move independently in a real body keep their rest transform."""
        for name in self.rig.get("locked", []):
            if name in self.s.index:
                self.local[self.i(name)] = self.s.rest_local[self.i(name)]
        self.refresh()


def drive(poser: Poser, breath: float = 0.0) -> dict:
    """Coupled motion of the non-deforming LM_ / AN_ joints (after the rig is posed):
    spine distribution, scapulohumeral rhythm, patellar tracking, breathing. Returns stats."""
    s, rig = poser.s, poser.rig
    W, B = poser.world.copy(), s.rest_world
    stats = {}
    chain = [j for j in rig["axial_chain"] if j in s.index]
    ci = [s.index[j] for j in chain]
    delta = {i: W[i] @ np.linalg.inv(B[i]) for i in ci}
    axial = set(ci[1:])                  # joints on the pelvis (chain root) stay rigid with it
    driven = {}

    def interp(p):
        """Chain segment and parameter by height (anterior points such as the sternum stay on their level)."""
        z = p[2]
        for a, b in zip(ci, ci[1:]):
            za, zb = B[a][2, 3], B[b][2, 3]
            if min(za, zb) <= z <= max(za, zb) and abs(zb - za) > 1e-6:
                return a, b, (z - za) / (zb - za)
        lowest = ci[int(np.argmin([B[i][2, 3] for i in ci]))]
        return (lowest, lowest, 0.0) if z < B[lowest][2, 3] else (ci[-1], ci[-1], 0.0)

    # 1. spine distribution: every annotation joint hanging off the axial chain blends its neighbours
    for i, name in enumerate(s.names):
        if not name.startswith(("LM_", "AN_")) or s.parents[i] not in axial:
            continue
        anchor = DRIVE_ANCHOR.get(name)
        a, b, t = interp(B[s.index[anchor]][:3, 3] if anchor in s.index else B[i][:3, 3])
        M = np.eye(4)
        M[:3, :3] = slerp(delta[a][:3, :3], delta[b][:3, :3], t) @ B[i][:3, :3]
        M[:3, 3] = (1 - t) * (delta[a] @ B[i][:, 3])[:3] + t * (delta[b] @ B[i][:, 3])[:3]
        driven[i] = M
    Wd = W.copy()
    for i, M in driven.items():
        Wd[i] = M
    pelvis_R = Wd[ci[0]][:3, :3] @ B[ci[0]][:3, :3].T
    for level in ("C2", "C7", "T1", "T4", "T7", "T10", "T12", "L1", "L3", "L5"):
        n = f"LM_{level}"
        if n in s.index:
            Rv = Wd[s.index[n]][:3, :3] @ B[s.index[n]][:3, :3].T
            rel = pelvis_R.T @ Rv
            stats.setdefault("vertebra_rotation_vs_pelvis_deg", {})[level] = round(
                math.degrees(math.acos(np.clip((np.trace(rel) - 1) / 2, -1, 1))), 2)
    P = lambda n: Wd[s.index[n]][:3, 3].copy()                       # noqa: E731

    # 2. scapulohumeral rhythm: 1/3 of humeral elevation beyond 30 deg is scapular upward rotation
    rest_ang = angles(B, s)
    for side in SIDES:
        th, th0 = angles(Wd, s)[f"shoulder_elevation_{side}"], rest_ang[f"shoulder_elevation_{side}"]
        phi = (max(0.0, th - 30.0) - max(0.0, th0 - 30.0)) / 3.0
        names = [f"AN_scapula_{side}", f"LM_scapula_superior_angle_{side}", f"LM_scapula_spine_root_{side}",
                 f"LM_scapula_inferior_angle_{side}", f"LM_coracoid_{side}"]
        names = [n for n in names if n in s.index]
        if abs(phi) < 0.5 or not names:
            continue
        frame = Wd[s.index[f"AN_scapula_{side}"]]
        lat = -Wd[s.index["AN_thorax"]][:3, 2] if side == "L" else Wd[s.index["AN_thorax"]][:3, 2]
        best = None
        for sg in (1.0, -1.0):
            M = about(rot(frame[:3, 0], sg * phi), frame[:3, 3])
            moved = (M @ np.append(P(f"LM_scapula_inferior_angle_{side}"), 1))[:3]
            gain = (moved - P(f"LM_scapula_inferior_angle_{side}")) @ lat * np.sign(phi)
            if best is None or gain > best[0]:
                best = (gain, M)
        for n in names:
            Wd[s.index[n]] = best[1] @ Wd[s.index[n]]
            driven[s.index[n]] = Wd[s.index[n]]
        stats[f"scapular_upward_rotation_deg_{side}"] = round(phi, 2)

    # 3. patellar tracking: the patella follows ~70 % of the knee flexion around the femoral condyles
    for side in SIDES:
        name = f"LM_patella_internal_{side}"
        if name not in s.index:
            continue
        dflex = angles(Wd, s)[f"knee_flexion_{side}"] - rest_ang[f"knee_flexion_{side}"]
        if abs(dflex) < 0.5:
            continue
        axis = P(f"LM_lateral_femoral_epicondyle_{side}") - P(f"LM_medial_femoral_epicondyle_{side}")
        centre, hip = P(f"LM_knee_centre_{side}"), P(f"LM_hip_centre_{side}")
        options = [about(rot(axis, sg * 0.7 * dflex), centre) for sg in (1.0, -1.0)]
        dist = [np.linalg.norm((M @ Wd[s.index[name]])[:3, 3] - hip) for M in options]
        M = options[int(np.argmax(dist))] if dflex > 0 else options[int(np.argmin(dist))]
        Wd[s.index[name]] = M @ Wd[s.index[name]]
        driven[s.index[name]] = Wd[s.index[name]]
        stats[f"patella_tracking_deg_{side}"] = round(0.7 * dflex, 2)

    # 4. breathing: rib elevation (pump handle above, mixed pump / bucket handle below), sternum follows
    if breath > 0:
        thorax_right = Wd[s.index["AN_thorax"]][:3, 2]
        moves = []
        for k in range(1, 13):
            for side in SIDES:
                rib, end = f"AN_rib{k:02d}_{side}", f"LM_rib{k:02d}_end_{side}"
                if rib not in s.index or end not in s.index:
                    continue
                o, e = P(rib), P(end)
                axis = thorax_right if k <= 6 else _unit(_unit(thorax_right) + _unit(e - o))
                deg = breath * BREATH_DEG[k - 1]
                cand = [about(rot(axis, sg * deg), o) for sg in (1.0, -1.0)]
                M = max(cand, key=lambda m: (m @ np.append(e, 1))[2])
                for n in (rib, end):
                    Wd[s.index[n]] = M @ Wd[s.index[n]]
                    driven[s.index[n]] = Wd[s.index[n]]
                if k <= 7:
                    moves.append(P(end) - e)
        if moves:
            shift = np.mean(moves, axis=0)
            for n in ("AN_manubrium", "AN_sternum_body", "AN_xiphoid_process"):
                if n in s.index:
                    Wd[s.index[n]][:3, 3] += shift
                    driven[s.index[n]] = Wd[s.index[n]]
            stats["sternum_displacement_mm"] = [round(float(v) * 1000, 1) for v in shift]
            stats["sternum_anterior_mm"] = round(float(shift @ ANTERIOR) * 1000, 1)
            stats["sternum_superior_mm"] = round(float(shift @ SUPERIOR) * 1000, 1)

    # back to local transforms (parents of driven joints are rig bones, never driven themselves)
    for i, M in driven.items():
        p = s.parents[i]
        poser.local[i] = np.linalg.inv(Wd[p]) @ M
    poser.refresh()
    return stats


def pose(skel: Skeleton, rig: dict, stature: float, spec: dict, rom: dict = None) -> dict:
    """Pose one exam -> {"local", "world", "angles", "violations", "stats"}."""
    poser = Poser(skel, rig, stature)
    poser.apply(spec)
    stats = dict(poser.stats)
    stats.update(drive(poser, spec.get("breath", 0.0)))
    rest = angles(skel.rest_world, skel)
    clin = clinical(angles(poser.world, skel), rest)
    return {"local": poser.local, "world": poser.world, "angles": clin,
            "violations": validate(clin, rom), "stats": stats}
