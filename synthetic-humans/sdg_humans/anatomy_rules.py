"""Anatomical joints derived from the landmarks, and per-patient spinal shape (numpy only).

Shared verbatim by the MPFB (synthetic-humans) and MHR (mhr-synthetic-human) pipelines.
USD space: metres, Z-up, anterior = -Y, subject's left = +X. Frame axes (columns): X anterior,
Y superior, Z subject right, unless stated otherwise.

derived_joints(P, skin, stature) -> {name: {"position", "kind", ["axes"]}}
    joint centres   LM_<j>_centre_<s>   hip (Harrington 2007), shoulder (Rab 2002), elbow, wrist,
                                         knee, ankle (ISB midpoints of epicondyles / styloids / malleoli)
    rib cage        AN_rib01..12_<s>     costovertebral joints, X along the rib towards its anterior end
                    LM_rib01..12_end_<s> anterior (costochondral / sternal) rib ends
                    AN_manubrium, AN_sternum_body, AN_xiphoid_process
    foot axes       AN_talocrural_<s>    Z along the malleolar axis (towards the subject's right)
                    AN_subtalar_<s>      X along the subtalar axis (Inman: 42 deg up, 23 deg medial)
    internal        LM_hyoid, LM_carpus_<s>, LM_calcaneus_<s>, LM_patella_internal_<s>
sample_spine_shape / reshape_spine / spine_curvature: kyphosis, lordosis and scoliosis (Cobb angles).
"""

import fnmatch
import math

import numpy as np

from . import landmark_rules as rules

SIDES = (("L", 1.0), ("R", -1.0))
POSTERIOR = -rules.ANTERIOR

# Rib geometry (same defaults as the MPFB anatomy meshes, configs/anatomy.yaml)
RIB_DROP_CM = (3.0, 5.0, 7.0, 8.0, 9.0, 9.5, 9.5, 9.5, 9.0, 8.0, 6.0, 5.0)        # anterior end below its vertebra
RIB_END_DEG = (14, 14, 14, 14, 14, 16, 20, 32, 42, 55, 85, 100)                   # anterior end, from the front midline
RIB_WIDTH = (0.55, 0.70, 0.80, 0.88, 0.94, 0.98, 1.0, 1.0, 1.0, 0.98, 0.95, 0.90)  # x chest half-width
CHEST_HALF_WIDTH_OF_ACROMION = 0.80


def _unit(v):
    v = np.asarray(v, dtype=np.float64)
    return v / (np.linalg.norm(v) or 1.0)


def parent_lookup(name: str, mapping: dict, default=None):
    """Exact key first, then shell-style patterns ('rib*_L')."""
    if name in mapping:
        return mapping[name]
    for key, value in mapping.items():
        if any(c in key for c in "*?[") and fnmatch.fnmatchcase(name, key):
            return value
    return default


# --- joint centres -----------------------------------------------------------------------

def joint_centres(P: dict) -> dict:
    out = {}
    if all(k in P for k in ("asis_L", "asis_R", "psis_L", "psis_R")):
        origin, axes = rules.anatomical_frames({k: P[k] for k in ("asis_L", "asis_R", "psis_L", "psis_R")})["pelvis"]
        pw = np.linalg.norm(P["asis_R"] - P["asis_L"]) * 1000.0
        pd = np.linalg.norm((P["asis_L"] + P["asis_R"]) / 2 - (P["psis_L"] + P["psis_R"]) / 2) * 1000.0
        for sfx, s in SIDES:                                    # Harrington et al. 2007 (mm, pelvis frame)
            local = np.array([-0.24 * pd - 9.9, -0.30 * pw - 10.9, -s * (0.33 * pw + 7.3)]) / 1000.0
            out[f"hip_centre_{sfx}"] = origin + axes @ local
    if "acromion_L" in P and "acromion_R" in P:
        drop = 0.17 * np.linalg.norm(P["acromion_L"] - P["acromion_R"])      # Rab et al. 2002
        for sfx, _ in SIDES:
            out[f"shoulder_centre_{sfx}"] = P[f"acromion_{sfx}"] - rules.SUPERIOR * drop
    pairs = {"elbow": ("lateral_epicondyle", "medial_epicondyle"), "wrist": ("radial_styloid", "ulnar_styloid"),
             "knee": ("lateral_femoral_epicondyle", "medial_femoral_epicondyle"),
             "ankle": ("lateral_malleolus", "medial_malleolus")}
    for joint, (a, b) in pairs.items():
        for sfx, _ in SIDES:
            if f"{a}_{sfx}" in P and f"{b}_{sfx}" in P:
                out[f"{joint}_centre_{sfx}"] = (P[f"{a}_{sfx}"] + P[f"{b}_{sfx}"]) / 2
    return out


# --- rib cage ----------------------------------------------------------------------------

def rib_cage(P: dict, stature: float) -> dict:
    """Rib and sternum joints (schematic, scaled from the trunk landmarks)."""
    k = stature / 1.70
    need = ["jugular_notch", "sternal_angle", "xiphoid", "T4_surf", "acromion_L"] + [f"T{i}" for i in range(1, 13)]
    if not all(n in P for n in need):
        return {}
    depth = abs(P["T4_surf"][1] - P["sternal_angle"][1])
    soft = max(0.010, 0.06 * depth)                                  # skin -> bone in front of the sternum
    out = {}
    jn, sa, xp = (P[n] + POSTERIOR * soft for n in ("jugular_notch", "sternal_angle", "xiphoid"))
    up = _unit(jn - xp)
    for name, origin in (("manubrium", jn), ("sternum_body", sa), ("xiphoid_process", xp)):
        out[name] = {"position": origin, "kind": "frame", "frame": name,
                     "axes": rules.frame_from(rules.RIGHT, np.cross(up, rules.RIGHT))}
    half = CHEST_HALF_WIDTH_OF_ACROMION * abs(P["acromion_L"][0]) - soft
    for i in range(12):
        v = P[f"T{i + 1}"]
        z_end = v[2] - RIB_DROP_CM[i] / 100.0 * k
        t = np.clip((jn[2] - z_end) / max(jn[2] - xp[2], 1e-6), 0.0, 1.0)
        y_front = jn[1] + (xp[1] - jn[1]) * t                         # sternum line at that height
        y_back = v[1] + 0.25 * (P["T4_surf"][1] - P["T4"][1])          # rib angles, a quarter of the way to the skin
        yc, a = (y_front + y_back) / 2, (y_back - y_front) / 2
        theta = math.radians(RIB_END_DEG[i])
        for sfx, s in SIDES:
            origin = v + np.array([s * 0.025 * k, 0.012 * k, 0.0])
            end = np.array([s * half * RIB_WIDTH[i] * math.sin(theta), yc - a * math.cos(theta), z_end])
            rib = f"rib{i + 1:02d}_{sfx}"
            out[rib] = {"position": origin, "kind": "frame", "frame": rib, "rib": i + 1,
                        "axes": rules.frame_from(rules.RIGHT, end - origin)}
            out[f"rib{i + 1:02d}_end_{sfx}"] = {"position": end, "kind": "internal", "rib": i + 1}
    # frame_from() returns X = anterior hint; for ribs that hint is the rib direction (X along the rib)
    return out


# --- foot axes ---------------------------------------------------------------------------

def foot_axes(P: dict, stature: float) -> dict:
    k = stature / 1.70
    out = {}
    for sfx, s in SIDES:
        need = [f"lateral_malleolus_{sfx}", f"medial_malleolus_{sfx}", f"heel_{sfx}",
                f"metatarsal_head_1_{sfx}", f"metatarsal_head_5_{sfx}"]
        if not all(n in P for n in need):
            continue
        lat, med, heel = P[need[0]], P[need[1]], P[need[2]]
        centre = (lat + med) / 2
        toes = (P[need[3]] + P[need[4]]) / 2
        foot = _unit((toes - heel) * np.array([1.0, 1.0, 0.0]))      # long axis, horizontal
        right = (med - lat) if s > 0 else (lat - med)
        out[f"talocrural_{sfx}"] = {"position": centre, "kind": "frame", "frame": f"talocrural_{sfx}",
                                    "axes": rules.frame_from(right, foot)}
        medial = np.array([-s, 0.0, 0.0])
        horiz = _unit(math.cos(math.radians(23)) * foot + math.sin(math.radians(23)) * medial)
        axis = _unit(math.cos(math.radians(42)) * horiz + math.sin(math.radians(42)) * rules.SUPERIOR)
        z = _unit(rules.RIGHT - (rules.RIGHT @ axis) * axis)
        out[f"subtalar_{sfx}"] = {"position": centre - rules.SUPERIOR * 0.02 * k, "kind": "frame",
                                  "frame": f"subtalar_{sfx}", "axes": np.column_stack([axis, np.cross(z, axis), z])}
    return out


# --- other internal points ---------------------------------------------------------------

def internal_points(P: dict, skin, stature: float, centres: dict) -> dict:
    k = stature / 1.70
    out = {}
    if "C3" in P and skin is not None:
        c3 = P["C3"]
        front = skin[(np.abs(skin[:, 0]) < 0.006) & (np.abs(skin[:, 2] - c3[2]) < 0.01 * k) & (skin[:, 1] < c3[1])]
        if len(front):
            neck_front = front[np.argmin(front[:, 1])]
            out["hyoid"] = {"position": neck_front + (c3 - neck_front) * 0.25, "kind": "internal"}
    for sfx, _ in SIDES:
        if f"wrist_centre_{sfx}" in centres and f"elbow_centre_{sfx}" in centres:
            w, e = centres[f"wrist_centre_{sfx}"], centres[f"elbow_centre_{sfx}"]
            out[f"carpus_{sfx}"] = {"position": w + _unit(w - e) * 0.02 * k, "kind": "internal"}
        if f"heel_{sfx}" in P:
            out[f"calcaneus_{sfx}"] = {"position": P[f"heel_{sfx}"] + (rules.ANTERIOR * 0.03 + rules.SUPERIOR * 0.025) * k,
                                       "kind": "internal"}
        if f"patella_{sfx}" in P:
            out[f"patella_internal_{sfx}"] = {"position": P[f"patella_{sfx}"] + POSTERIOR * 0.012 * k,
                                              "kind": "internal"}
    return out


def derived_joints(P: dict, skin, stature: float) -> dict:
    """All derived joints. P: {landmark name: position} incl. spine levels (T4, T4_surf, ...)."""
    P = {k: np.asarray(v, dtype=np.float64) for k, v in P.items()}
    centres = joint_centres(P)
    out = {f"{name}": {"position": pos, "kind": "centre"} for name, pos in centres.items()}
    out.update(rib_cage(P, stature))
    out.update(foot_axes(P, stature))
    out.update(internal_points(P, skin, stature, centres))
    return out


# --- spinal shape ------------------------------------------------------------------------

def _tangents(c):
    c = np.asarray(c)
    t = np.empty_like(c)
    t[1:-1] = c[:-2] - c[2:]                                         # cranial direction (list is cranio-caudal)
    t[0], t[-1] = c[0] - c[1], c[-2] - c[-1]
    return t / np.linalg.norm(t, axis=1, keepdims=True)


def spine_curvature(centres, levels) -> dict:
    """Cobb-style angles (deg) of the vertebral-body curve.
    kyphosis T4-T12 (positive = convex posterior), lordosis L1-S1 (positive = convex anterior),
    scoliosis = largest frontal-plane angle between two vertebrae T1-L5."""
    t = _tangents(centres)
    i = {lv: n for n, lv in enumerate(levels)}
    sag = np.degrees(np.arctan2(t[:, 1], t[:, 2]))                  # + = tilted posteriorly
    front = np.degrees(np.arctan2(t[:, 0], t[:, 2]))
    region = [i[lv] for lv in levels if lv[0] in "TL"]
    sc = front[region]
    return {"kyphosis_T4_T12_deg": round(float(sag[i["T12"]] - sag[i["T4"]]), 2),
            "lordosis_L1_S1_deg": round(float(sag[i["L1"]] - sag[i["S1"]]), 2),
            "scoliosis_cobb_deg": round(float(sc.max() - sc.min()), 2)}


def sample_spine_shape(rng, age: float, cfg: dict) -> dict:
    """Per-patient targets: kyphosis grows with age, scoliosis prevalence grows with age."""
    ky, lo, sc = cfg["kyphosis_deg"], cfg["lordosis_deg"], cfg["scoliosis"]
    kyph = ky["mean_at_20"] + ky["per_year_after_20"] * max(0.0, age - 20.0) + rng.normal(0.0, ky["sd"])
    lord = lo["mean"] + rng.normal(0.0, lo["sd"])
    p = sc["prevalence_at_40"] + sc["per_year_after_40"] * max(0.0, age - 40.0)
    shape = {"kyphosis_T4_T12_deg": float(np.clip(kyph, ky["min"], ky["max"])),
             "lordosis_L1_S1_deg": float(np.clip(lord, lo["min"], lo["max"])),
             "scoliosis_cobb_deg": 0.0, "scoliosis_apex": None, "scoliosis_convex": None}
    if rng.random() < p:
        shape["scoliosis_cobb_deg"] = float(rng.uniform(*sc["cobb_range_deg"]))
        shape["scoliosis_apex"] = str(rng.choice(sc["apex_levels"]))
        shape["scoliosis_convex"] = str(rng.choice(["right", "left"]))
    return shape


def _bump(levels, lo, hi, apex=None):
    """Smooth weights (sum 1) over the levels lo..hi (inclusive), peaking at the apex."""
    i0, i1 = levels.index(lo), levels.index(hi)
    w = np.zeros(len(levels))
    ia = levels.index(apex) if apex else (i0 + i1) / 2
    for n in range(i0, i1 + 1):
        span = (ia - i0 + 1) if n <= ia else (i1 - ia + 1)
        w[n] = math.cos(0.5 * math.pi * (n - ia) / span) ** 2
    return w / w.sum()


def _bend(centres, kappa, axis_index):
    """Add curvature kappa (rad per vertebra) about a world axis, rebuilding from the bottom (S5 fixed),
    then remove the drift at C1 linearly along the arc so the curve stays inside the body."""
    c = np.asarray(centres, dtype=np.float64)
    n = len(c)
    out = c.copy()
    angle = 0.0
    for i in range(n - 2, -1, -1):                                   # from the sacrum upwards
        angle += kappa[i + 1]
        seg = c[i] - c[i + 1]
        ca, sa = math.cos(angle), math.sin(angle)
        a, b = [(1, 2), (0, 2)][axis_index]                          # plane of the bend: YZ (sagittal) or XZ (frontal)
        r = seg.copy()
        r[a], r[b] = ca * seg[a] + sa * seg[b], -sa * seg[a] + ca * seg[b]
        out[i] = out[i + 1] + r
    drift = out[0] - c[0]
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(c[::-1], axis=0), axis=1))])[::-1]
    out -= np.outer(arc / arc[0], drift)
    return out


def _secant(f, target, x0=0.0, x1=0.2, tol=0.05, steps=12):
    """Solve f(x) = target for a scalar amplitude (robust to the sign conventions)."""
    f0, f1 = f(x0) - target, f(x1) - target
    for _ in range(steps):
        if abs(f1) < tol or f1 == f0:
            break
        x0, x1, f0 = x1, x1 - f1 * (x1 - x0) / (f1 - f0), f1
        f1 = f(x1) - target
    return x1


def reshape_spine(centres, levels, shape: dict):
    """-> (new centres, axial rotation per level in deg) matching the target Cobb angles.
    Curvature is added as smooth bumps (kyphosis T4-T12, lordosis L1-S1, scoliosis around its apex)."""
    levels = list(levels)
    c0 = np.asarray(centres, dtype=np.float64)
    wk, wl = _bump(levels, "T4", "T12"), _bump(levels, "L1", "S1")
    xk = xl = 0.0
    for _ in range(3):                                                # kyphosis and lordosis interact a little
        xk = _secant(lambda x: spine_curvature(_bend(c0, x * wk + xl * wl, 0), levels)["kyphosis_T4_T12_deg"],
                     shape["kyphosis_T4_T12_deg"], xk, xk + 0.1)
        xl = _secant(lambda x: spine_curvature(_bend(c0, xk * wk + x * wl, 0), levels)["lordosis_L1_S1_deg"],
                     shape["lordosis_L1_S1_deg"], xl, xl + 0.1)
    c = _bend(c0, xk * wk + xl * wl, 0)
    rotation = np.zeros(len(levels))
    if shape.get("scoliosis_cobb_deg"):
        apex = shape["scoliosis_apex"]
        lo, hi = ("T2", "T12") if apex[0] == "T" and int(apex[1:]) <= 9 else ("T9", "L4")
        w = _bump(levels, lo, hi, apex)
        sign = 1.0 if shape["scoliosis_convex"] == "left" else -1.0
        base = c
        xs = _secant(lambda x: spine_curvature(_bend(base, sign * abs(x) * w, 1), levels)["scoliosis_cobb_deg"],
                     shape["scoliosis_cobb_deg"], 0.05, 0.3)
        c = _bend(base, sign * abs(xs) * w, 1)
        apex_x = c[levels.index(apex), 0] - base[levels.index(apex), 0]
        if (apex_x > 0) != (sign > 0):                                # convexity towards the requested side
            c = _bend(base, -sign * abs(xs) * w, 1)
        rotation = sign * (shape["scoliosis_cobb_deg"] / 3.0) * w / w.max()   # axial rotation, max at the apex
    return c, rotation
