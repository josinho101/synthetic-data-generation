"""Rig-independent anatomical landmark rules (numpy only).

Shared verbatim by the MPFB (mpfb-humans) and MHR (mhr-synthetic-human) pipelines, so both
place the same landmark set by the same rules. Works on a neutral body in USD space:
metres, Z-up, subject faces -Y (anterior = -Y, posterior = +Y), subject's left = +X.

propose_anchors(points, refs) -> {anchor name: vertex index}
    points : (V, 3) skin vertices (no eyes, teeth, helpers)
    refs   : joint centres {hip_L, knee_L, ankle_L, ball_L (toe base), shoulder_L, elbow_L, wrist_L,
             eye_L, thumb_L, pinky_L, and the same for _R}
Levels on the trunk are stature fractions (ANSUR-style anthropometric heights); limb and head
landmarks are found around the reference joints.

anatomical_frames(lm) -> {frame name: (origin, 3x3 axes)}; columns X anterior, Y superior,
Z subject right (ISB-style, same directions on both sides).
"""

import numpy as np

SIDES = (("L", 1.0), ("R", -1.0))

# Trunk landmark heights as a fraction of stature (floor -> vertex).
STATURE_FRACTION = {
    "c7_spinous": 0.838, "t7_spinous": 0.745, "t12_spinous": 0.670, "l4_spinous": 0.590,
    "s1_spinous": 0.556, "coccyx": 0.509,
    "jugular_notch": 0.813, "sternal_angle": 0.783, "xiphoid": 0.723, "costal_margin": 0.668,
    "navel": (0.575, 0.650),           # search band; the deepest point is the navel
    "navel_fallback": 0.600,           # omphalion height when the mesh has no dimple
    "scapula_superior_angle": 0.824, "scapula_spine_root": 0.808, "scapula_inferior_angle": 0.745,
    "asis": 0.562, "psis": 0.556, "iliac_crest": 0.598, "pubic_symphysis": 0.515,
}

# Which rule found each anchor (documentation / metadata).
NAMES_BILATERAL = (
    "tragus", "outer_canthus", "infraorbital", "mastoid", "gonion",
    "acromion", "coracoid", "scapula_superior_angle", "scapula_spine_root", "scapula_inferior_angle",
    "costal_margin", "asis", "psis", "iliac_crest", "greater_trochanter",
    "lateral_epicondyle", "medial_epicondyle", "olecranon", "radial_styloid", "ulnar_styloid",
    "patella", "lateral_femoral_epicondyle", "medial_femoral_epicondyle", "fibular_head",
    "lateral_malleolus", "medial_malleolus", "heel", "metatarsal_head_1", "metatarsal_head_5",
)
NAMES_MIDLINE = (
    "vertex", "glabella", "nasion", "chin", "inion",
    "c7_spinous", "t7_spinous", "t12_spinous", "l4_spinous", "s1_spinous", "coccyx",
    "jugular_notch", "sternal_angle", "xiphoid", "navel", "pubic_symphysis",
)


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v) or 1.0)


class _Body:
    def __init__(self, points, refs):
        self.p = np.asarray(points, dtype=np.float64)
        self.r = {k: np.asarray(v, dtype=np.float64) for k, v in refs.items()}
        self.floor, self.top = self.p[:, 2].min(), self.p[:, 2].max()
        self.H = self.top - self.floor
        self.k = self.H / 1.70                                   # stature scale for fixed distances
        self.mid = np.flatnonzero(np.abs(self.p[:, 0]) < 0.006 * max(self.k, 0.5))
        hip_x = abs(self.r["hip_L"][0] - self.r["hip_R"][0]) / 2
        # trunk = not the arms (A-pose hands hang beside the hips)
        self.trunk = np.flatnonzero(np.abs(self.p[:, 0]) < hip_x + 0.11 * self.k)

    def z(self, frac):
        return self.floor + frac * self.H

    def pick(self, idx, score):
        idx = np.asarray(idx)
        if idx.size == 0:
            raise RuntimeError("landmark rule found no candidate vertices")
        return int(idx[np.argmax(score(self.p[idx]))])

    def band(self, idx, z, tol):
        idx = np.asarray(idx)
        return idx[np.abs(self.p[idx, 2] - z) < tol]

    def posterior_midline(self, z, tol=0.015):
        idx = self.band(self.mid[self.p[self.mid, 1] > -0.05], z, tol * self.k)
        return self.pick(idx, lambda q: q[:, 1] - np.abs(q[:, 2] - z))

    def anterior_midline(self, z, tol=0.015):
        idx = self.band(self.mid[self.p[self.mid, 1] < 0.0], z, tol * self.k)
        return self.pick(idx, lambda q: -q[:, 1] - np.abs(q[:, 2] - z))

    def soft(self, idx, primary, x=None, z=None, box=0.03, weight=2.0):
        """Best `primary` score within a box around |x| = x and z = z, penalised by the distance to them."""
        idx = np.asarray(idx)
        q = self.p[idx]
        keep = np.ones(len(idx), bool)
        penalty = np.zeros(len(idx))
        if x is not None:
            dx = np.abs(np.abs(q[:, 0]) - x)
            keep &= dx < box * self.k
            penalty += dx
        if z is not None:
            dz = np.abs(q[:, 2] - z)
            keep &= dz < box * self.k
            penalty += dz
        if not keep.any():
            raise RuntimeError("landmark rule found no candidate vertices")
        score = primary(q[keep]) - weight * penalty[keep]
        return int(idx[keep][np.argmax(score)])

    def near(self, centre, radius):
        return np.flatnonzero(np.linalg.norm(self.p - centre, axis=1) < radius)

    def nearest(self, target, idx=None):
        idx = np.arange(len(self.p)) if idx is None else np.asarray(idx)
        return int(idx[np.argmin(np.linalg.norm(self.p[idx] - target, axis=1))])

    def side(self, idx, s):
        idx = np.asarray(idx)
        return idx[self.p[idx, 0] * s > 0.0]


# --- head --------------------------------------------------------------------------------

def _head(b: _Body) -> dict:
    eye_l, eye_r = b.r["eye_L"], b.r["eye_R"]
    eye_z, eye_y = (eye_l[2] + eye_r[2]) / 2, (eye_l[1] + eye_r[1]) / 2
    vertex = b.pick(b.mid, lambda q: q[:, 2])
    fh = b.p[vertex, 2] - eye_z                                  # eye -> vertex, the head scale
    front = b.mid[b.p[b.mid, 1] < eye_y + 0.02]
    a = {"vertex": vertex,
         "inion": b.posterior_midline(eye_z - 0.25 * fh, 0.01),
         "nasion": b.anterior_midline(eye_z + 0.075 * fh, 0.006),
         "glabella": b.pick(front[(b.p[front, 2] > eye_z + 0.12 * fh) & (b.p[front, 2] < eye_z + 0.32 * fh)],
                            lambda q: -q[:, 1])}
    chin_band = front[(b.p[front, 2] > eye_z - 1.45 * fh) & (b.p[front, 2] < eye_z - 0.55 * fh)
                      & (b.p[front, 1] < eye_y - 0.01 * b.k)]
    a["chin"] = b.pick(chin_band, lambda q: -q[:, 2])
    head = np.flatnonzero(b.p[:, 2] > b.p[a["chin"], 2] - 0.01)
    for sfx, s in SIDES:
        eye = b.r[f"eye_{sfx}"]
        a[f"outer_canthus_{sfx}"] = b.nearest(eye + np.array([s * 0.013, 0.0, 0.004]) * b.k, head)
        orb = head[(np.abs(b.p[head, 0] - eye[0]) < 0.006 * b.k)
                   & (np.abs(b.p[head, 2] - (eye[2] - 0.018 * b.k)) < 0.005 * b.k)]
        a[f"infraorbital_{sfx}"] = b.pick(orb, lambda q: -q[:, 1])
        tz = eye_z - 0.11 * fh
        ear = b.side(head, s)
        ear = ear[(np.abs(b.p[ear, 2] - tz) < 0.012 * b.k)
                  & (b.p[ear, 1] > eye_y + 0.040 * b.k) & (b.p[ear, 1] < eye_y + 0.065 * b.k)]
        tragus = b.pick(ear, lambda q: q[:, 0] * s)
        a[f"tragus_{sfx}"] = tragus
        t = b.p[tragus]
        a[f"mastoid_{sfx}"] = b.nearest(t + np.array([-s * 0.012, 0.022, -0.028]) * b.k, b.side(head, s))
        jaw = b.side(head, s)
        jaw = jaw[(np.abs(b.p[jaw, 2] - (t[2] - 0.050 * b.k)) < 0.006 * b.k)
                  & (b.p[jaw, 1] > t[1] - 0.030 * b.k) & (b.p[jaw, 1] < t[1] - 0.008 * b.k)]   # in front of the ear lobe
        a[f"gonion_{sfx}"] = b.pick(jaw, lambda q: q[:, 0] * s)
    return a


# --- trunk -------------------------------------------------------------------------------

def _trunk(b: _Body) -> dict:
    f = STATURE_FRACTION
    a = {n: b.posterior_midline(b.z(f[n])) for n in
         ("c7_spinous", "t7_spinous", "t12_spinous", "l4_spinous", "s1_spinous", "coccyx")}
    a.update({n: b.anterior_midline(b.z(f[n])) for n in ("jugular_notch", "sternal_angle", "xiphoid")})
    lo, hi = f["navel"]
    front = b.mid[(b.p[b.mid, 1] < 0.0) & (b.p[b.mid, 2] > b.z(lo)) & (b.p[b.mid, 2] < b.z(hi))]
    navel = b.pick(front, lambda q: q[:, 1])                     # deepest front midline point
    if min(b.p[navel, 2] - b.z(lo), b.z(hi) - b.p[navel, 2]) < 0.01 * b.k:
        navel = b.anterior_midline(b.z(f["navel_fallback"]))     # no umbilical dimple in the mesh
    a["navel"] = navel
    a["pubic_symphysis"] = b.anterior_midline(b.z(f["pubic_symphysis"]), 0.01)
    for sfx, s in SIDES:
        sh, hip = b.r[f"shoulder_{sfx}"], b.r[f"hip_{sfx}"]
        acr = b.pick(b.near(sh, 0.09 * b.k), lambda q: q[:, 2] + 0.5 * q[:, 0] * s)
        a[f"acromion_{sfx}"] = acr
        ax = abs(b.p[acr, 0])
        torso = b.side(b.trunk, s)
        back = torso[b.p[torso, 1] > 0.0]
        frontt = torso[b.p[torso, 1] < 0.0]

        def back_at(frac, xfrac):
            return b.soft(back, lambda q: q[:, 1], x=xfrac * ax, z=b.z(f[frac]))

        a[f"scapula_superior_angle_{sfx}"] = back_at("scapula_superior_angle", 0.42)
        a[f"scapula_spine_root_{sfx}"] = back_at("scapula_spine_root", 0.38)
        a[f"scapula_inferior_angle_{sfx}"] = back_at("scapula_inferior_angle", 0.45)
        a[f"coracoid_{sfx}"] = b.soft(frontt, lambda q: -q[:, 1], x=0.78 * ax, z=b.p[acr, 2] - 0.035 * b.k)
        a[f"costal_margin_{sfx}"] = b.soft(frontt, lambda q: -q[:, 1], x=0.50 * ax, z=b.z(f["costal_margin"]))
        troch = b.pick(b.band(torso, hip[2], 0.008 * b.k), lambda q: q[:, 0] * s)
        a[f"greater_trochanter_{sfx}"] = troch
        # inter-ASIS ~ 0.75 x bitrochanteric width
        a[f"asis_{sfx}"] = b.soft(frontt, lambda q: -q[:, 1], x=0.75 * abs(b.p[troch, 0]), z=b.z(f["asis"]))
        a[f"psis_{sfx}"] = b.soft(back, lambda q: q[:, 1], x=0.045 * b.k, z=b.z(f["psis"]), weight=4.0)
        a[f"iliac_crest_{sfx}"] = b.pick(b.band(torso, b.z(f["iliac_crest"]), 0.008 * b.k), lambda q: q[:, 0] * s)
    return a


# --- limbs -------------------------------------------------------------------------------

def _limbs(b: _Body) -> dict:
    a = {}
    for sfx, s in SIDES:
        sh, el, wr = b.r[f"shoulder_{sfx}"], b.r[f"elbow_{sfx}"], b.r[f"wrist_{sfx}"]
        u, w = _unit(el - sh), _unit(wr - el)
        axis = np.cross(u, w)
        if np.linalg.norm(axis) < 0.15:                          # straight elbow: coronal plane normal
            axis = np.cross(u, [0.0, -1.0, 0.0])
        axis = _unit(axis)
        lateral = axis if (axis[2] + axis[0] * s) > 0 else -axis  # lateral side = up/out in an A-pose
        ring = b.near(el, 0.07 * b.k)
        ring = ring[np.abs((b.p[ring] - el) @ u) < 0.015 * b.k]
        a[f"lateral_epicondyle_{sfx}"] = b.pick(ring, lambda q: (q - el) @ lateral)
        a[f"medial_epicondyle_{sfx}"] = b.pick(ring, lambda q: -(q - el) @ lateral)
        back = _unit(np.cross(lateral, u))                       # posterior side of the elbow
        if back[1] < 0:
            back = -back
        ole = b.near(el, 0.07 * b.k)
        ole = ole[np.abs((b.p[ole] - el) @ u - 0.005 * b.k) < 0.02 * b.k]
        a[f"olecranon_{sfx}"] = b.pick(ole, lambda q: (q - el) @ back)
        radial = b.r[f"thumb_{sfx}"] - wr
        radial = _unit(radial - (radial @ w) * w)
        dist = b.near(wr, 0.06 * b.k)
        t = (b.p[dist] - wr) @ w
        dist = dist[(t > -0.030 * b.k) & (t < -0.005 * b.k)]
        a[f"radial_styloid_{sfx}"] = b.pick(dist, lambda q: (q - wr) @ radial)
        a[f"ulnar_styloid_{sfx}"] = b.pick(dist, lambda q: -(q - wr) @ radial)

        kn, an = b.r[f"knee_{sfx}"], b.r[f"ankle_{sfx}"]
        leg = b.side(b.near(kn, 0.09 * b.k), s)
        pat = leg[(b.p[leg, 2] > kn[2]) & (b.p[leg, 2] < kn[2] + 0.04 * b.k) & (np.abs(b.p[leg, 0] - kn[0]) < 0.03 * b.k)]
        a[f"patella_{sfx}"] = b.pick(pat, lambda q: -q[:, 1])
        epi = leg[(np.abs(b.p[leg, 2] - (kn[2] + 0.012 * b.k)) < 0.010 * b.k) & (np.abs(b.p[leg, 1] - kn[1]) < 0.03 * b.k)]
        a[f"lateral_femoral_epicondyle_{sfx}"] = b.pick(epi, lambda q: q[:, 0] * s)
        a[f"medial_femoral_epicondyle_{sfx}"] = b.pick(epi, lambda q: -q[:, 0] * s)
        fib = leg[(np.abs(b.p[leg, 2] - (kn[2] - 0.025 * b.k)) < 0.008 * b.k) & (b.p[leg, 1] > kn[1] - 0.01 * b.k)]
        a[f"fibular_head_{sfx}"] = b.pick(fib, lambda q: q[:, 0] * s)
        foot = b.side(b.near(an, 0.07 * b.k), s)
        foot = foot[np.abs(b.p[foot, 1] - an[1]) < 0.025 * b.k]
        lat = foot[np.abs(b.p[foot, 2] - (an[2] - 0.008 * b.k)) < 0.008 * b.k]
        med = foot[np.abs(b.p[foot, 2] - (an[2] + 0.004 * b.k)) < 0.008 * b.k]
        a[f"lateral_malleolus_{sfx}"] = b.pick(lat, lambda q: q[:, 0] * s)
        a[f"medial_malleolus_{sfx}"] = b.pick(med, lambda q: -q[:, 0] * s)
        a[f"heel_{sfx}"] = b.pick(b.side(np.flatnonzero(b.p[:, 2] < b.floor + 0.05 * b.k), s), lambda q: q[:, 1])
        ball = b.r[f"ball_{sfx}"]
        fore = b.side(b.near(ball, 0.08 * b.k), s)
        fore = fore[(np.abs(b.p[fore, 1] - ball[1]) < 0.015 * b.k) & (b.p[fore, 2] < ball[2] + 0.04 * b.k)]
        a[f"metatarsal_head_1_{sfx}"] = b.pick(fore, lambda q: -q[:, 0] * s)
        a[f"metatarsal_head_5_{sfx}"] = b.pick(fore, lambda q: q[:, 0] * s)
    return a


def propose_anchors(points, refs) -> dict:
    b = _Body(points, refs)
    anchors = {}
    for rule in (_head, _trunk, _limbs):
        anchors.update(rule(b))
    return anchors


# --- anatomical frames -------------------------------------------------------------------

RIGHT = np.array([-1.0, 0.0, 0.0])
ANTERIOR = np.array([0.0, -1.0, 0.0])
SUPERIOR = np.array([0.0, 0.0, 1.0])


def frame_from(z_hint, x_hint):
    """Orthonormal axes (columns X anterior, Y superior, Z right) from a right and an anterior hint."""
    z = _unit(z_hint)
    x = _unit(np.asarray(x_hint) - (np.asarray(x_hint) @ z) * z)
    y = np.cross(z, x)
    return np.column_stack([x, y, z])


def anatomical_frames(lm: dict) -> dict:
    """lm: {landmark name: position (3,)} (rest pose). Missing inputs skip that frame."""
    P = {k: np.asarray(v, dtype=np.float64) for k, v in lm.items()}
    frames = {}
    if all(k in P for k in ("asis_L", "asis_R", "psis_L", "psis_R")):
        mid_asis, mid_psis = (P["asis_L"] + P["asis_R"]) / 2, (P["psis_L"] + P["psis_R"]) / 2
        frames["pelvis"] = (mid_asis, frame_from(P["asis_R"] - P["asis_L"], mid_asis - mid_psis))
    if all(k in P for k in ("jugular_notch", "xiphoid", "C7_surf", "T8_surf")):
        ij, px, c7, t8 = P["jugular_notch"], P["xiphoid"], P["C7_surf"], P["T8_surf"]
        y = _unit((ij + c7) / 2 - (px + t8) / 2)
        z = np.cross(ij - (px + t8) / 2, c7 - (px + t8) / 2)       # normal of the sagittal plane
        z = _unit(z if z @ RIGHT > 0 else -z)
        x = np.cross(y, z)
        frames["thorax"] = (ij, frame_from(z, x))
    for sfx, s in SIDES:
        need = (f"acromion_{sfx}", f"scapula_spine_root_{sfx}", f"scapula_inferior_angle_{sfx}")
        if all(k in P for k in need):
            aa, ts, ai = (P[k] for k in need)
            zr = (aa - ts) if s < 0 else (ts - aa)                 # always towards the subject's right
            n = np.cross(ts - aa, ai - aa)
            n = n if n @ ANTERIOR > 0 else -n
            frames[f"scapula_{sfx}"] = (aa, frame_from(zr, n))
    if all(k in P for k in ("tragus_L", "tragus_R", "infraorbital_L", "infraorbital_R")):
        mid_t = (P["tragus_L"] + P["tragus_R"]) / 2
        mid_o = (P["infraorbital_L"] + P["infraorbital_R"]) / 2
        frames["skull"] = (mid_t, frame_from(P["tragus_R"] - P["tragus_L"], mid_o - mid_t))   # Frankfort plane
    return frames


def spine_axes(points: list) -> list:
    """Axes per vertebral body centre (cranio-caudal list): Y along the curve (cranial), Z right."""
    pts = np.asarray(points, dtype=np.float64)
    axes = []
    for i in range(len(pts)):
        up = pts[max(i - 1, 0)] - pts[min(i + 1, len(pts) - 1)]
        y = _unit(up)
        z = _unit(RIGHT - (RIGHT @ y) * y)
        axes.append(np.column_stack([np.cross(y, z), y, z]))
    return axes
