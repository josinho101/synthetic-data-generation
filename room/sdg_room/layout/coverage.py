"""Camera coverage of the patient: sample points of everything a patient does in the X-ray room, 3-D occluders,
frustum + occlusion tests, and auto-framing (aim + widest-needed lens) of a camera at a mount position.

Point groups (room frame):
  marker     patient standing on the floor marker: feet to head, arms out
  walk_path  the walk entrance -> changing-room door -> floor marker (grid path): hips + head (the body)
  walk_feet  the same path at feet height (furniture often hides feet; reported, not required)
  support    patient lying on the table / stretcher (if present)
  room       the exam-area floor (full room view)
"""

import math
from collections import deque

import numpy as np

from .geometry import Rect
from .solver import collimator_front, transform_rect

GROUPS = ("marker", "walk_path", "walk_feet", "support", "room")


# --- sample points -----------------------------------------------------------------------------------------
def _walk_grid_path(spec, cfg, start, goal):
    """Shortest 4-connected grid path (cell centres) from start to the free cell nearest to goal."""
    walk = cfg["room"]["walk"]
    g, r = walk["grid_m"], walk["agent_radius_m"]
    L, W = spec["footprint_m"]
    xs, ys = np.arange(g / 2, L, g), np.arange(g / 2, W, g)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    blocked = (X < r) | (Y < r) | (X > L - r) | (Y > W - r)
    for rect in spec["layout"]["obstacles"].values():
        x0, y0, x1, y1 = rect
        dx = np.maximum(np.maximum(x0 - X, 0.0), X - x1)
        dy = np.maximum(np.maximum(y0 - Y, 0.0), Y - y1)
        blocked |= dx * dx + dy * dy < r * r

    def cell(p):
        return min(max(int(p[0] / g), 0), len(xs) - 1), min(max(int(p[1] / g), 0), len(ys) - 1)

    s = cell(start)
    if blocked[s]:
        return []
    parent = {s: None}
    queue = deque([s])
    goal_cells = (X - goal[0]) ** 2 + (Y - goal[1]) ** 2 <= 0.35 ** 2
    end = None
    while queue:
        c = queue.popleft()
        if goal_cells[c]:
            end = c
            break
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (c[0] + d[0], c[1] + d[1])
            if 0 <= n[0] < len(xs) and 0 <= n[1] < len(ys) and n not in parent and not blocked[n]:
                parent[n] = c
                queue.append(n)
    path = []
    while end is not None:
        path.append((float(xs[end[0]]), float(ys[end[1]])))
        end = parent[end]
    return path[::-1]


def _subsample(path, spacing):
    out, acc = [], spacing
    for i, p in enumerate(path):
        if i:
            acc += math.dist(p, path[i - 1])
        if acc >= spacing or i == len(path) - 1:
            out.append(p)
            acc = 0.0
    return out


def patient_points(spec: dict, cfg: dict) -> dict:
    cov = cfg["cameras"]["coverage"]
    lay = spec["layout"]
    groups = {}
    sx, sy = lay["marker"]["stand_point"]
    yaw = math.radians(lay["marker"]["yaw_deg"])
    side = (math.cos(yaw), math.sin(yaw))          # marker frame +X = the patient's left/right
    pts = [[sx, sy, z] for z in cov["marker_heights_m"]]
    for z in (1.0, 1.4):
        pts += [[sx + k * 0.35 * side[0], sy + k * 0.35 * side[1], z] for k in (-1, 1)]
    groups["marker"] = pts

    cr = lay["changing_room"]
    path = (_walk_grid_path(spec, cfg, lay["walk_start"], cr["point_outside"]) +
            _walk_grid_path(spec, cfg, cr["point_outside"], lay["marker"]["stand_point"]))
    steps = _subsample(path, cov["walk_spacing_m"])
    groups["walk_path"] = [[x, y, z] for x, y in steps for z in cov["walk_heights_m"]]
    groups["walk_feet"] = [[x, y, cov.get("feet_height_m", 0.1)] for x, y in steps]

    sup = lay.get("patient_support")
    if sup:
        r = Rect.from_list(sup["rect"])
        z = sup["size_m"][2] + 0.2
        groups["support"] = [[x, y, z] for x in np.linspace(r.x0 + 0.15, r.x1 - 0.15, 4)
                             for y in (r.cy - r.sy / 4, r.cy + r.sy / 4)]
    else:
        groups["support"] = []

    L, W = spec["footprint_m"]
    block = Rect.from_list(cr["block"])
    step = cov["room_grid_m"]
    groups["room"] = [[float(x), float(y), 0.02] for x in np.arange(0.15, L - 0.1, step)
                      for y in np.arange(0.15, W - 0.1, step) if not block.inflate(0.05).contains(x, y)]
    return {k: np.array(v, dtype=float).reshape(-1, 3) for k, v in groups.items()}


# --- occluders -----------------------------------------------------------------------------------------------
def _box(rect: Rect, z0, z1):
    return [rect.x0, rect.y0, z0, rect.x1, rect.y1, z1]


def occluders(spec: dict, cfg: dict) -> np.ndarray:
    """Axis-aligned 3-D boxes (room frame) of everything that can hide the patient from a camera."""
    lay, eq_cfg = spec["layout"], cfg["equipment"]
    H = spec["ceiling_height_m"]
    eq = lay["equipment"]
    boxes = []
    heights = {p["name"]: p["size_m"][2] for p in lay.get("props", [])}
    if lay.get("patient_support"):
        heights[lay["patient_support"]["kind"]] = lay["patient_support"]["size_m"][2]
    heights.update(bench=0.46, changing_chair=0.85)
    for name, rect in lay["obstacles"].items():
        if name in ("wall_stand", "tube_stand") or name.startswith("camera_stand_"):
            continue
        z1 = H if name.startswith("partition") or name == "wall_conduit" else heights.get(name, 1.0)
        boxes.append(_box(Rect.from_list(rect), 0.0, z1))

    # exam-camera tripods: thin legs, only the camera head blocks a view
    for stand in (lay.get("exam_cameras") or {}).values():
        x, y, z = stand["position"]
        boxes.append(_box(Rect.centered(x, y, 0.15, 0.15), z - 0.05, z + 0.05))

    # wall stand: column (to its top) + detector housing around the carriage height
    ws, ws_cfg, det = eq["wall_stand"], eq_cfg["wall_stand"], eq_cfg["detector"]
    (ox, oy), yaw = ws["origin"], ws["yaw_deg"]
    cw, cd = ws_cfg["column_size_m"]
    gap = ws_cfg["wall_gap_m"]
    hw, hh, hd = det["housing_size_m"]
    h = ws["detector_center_height_m"]
    boxes.append(_box(transform_rect(Rect(-cw / 2, gap, cw / 2, gap + cd), ox, oy, yaw), 0.0, ws["column_height_m"]))
    boxes.append(_box(transform_rect(Rect(-hw / 2, gap + cd, hw / 2, gap + cd + hd), ox, oy, yaw), h - hh / 2, h + hh / 2))

    # tube stand: carriage + column, arm + tube head around the tube height
    ts, t_cfg = eq["tube_stand"], eq_cfg["tube_stand"]
    (ox, oy), yaw = ts["origin"], ts["yaw_deg"]
    cx, ro = ts["carriage_x_m"], t_cfg["rail_offset_m"]
    colw, cold = t_cfg["column_size_m"]
    col_top = H if ts["column_type"] == "floor_ceiling" else ts["column_height_m"] + 0.15
    boxes.append(_box(transform_rect(Rect(cx - colw / 2, ro - cold / 2, cx + colw / 2, ro + cold / 2), ox, oy, yaw),
                      0.0, col_top))
    hl, hr = t_cfg["housing_length_m"], t_cfg["housing_radius_m"]
    ch = t_cfg["collimator_size_m"][2]
    f_off = ts["focal_offset_m"]
    # thin horizontal arm from the column to the tube head (a long arm in a wide room must not act as a wall)
    aw, ah = t_cfg["arm_size_m"]
    arm = Rect(cx - aw / 2 - 0.03, ro, cx + aw / 2 + 0.03, max(ro, f_off - hr))
    boxes.append(_box(transform_rect(arm, ox, oy, yaw), h - ah / 2 - 0.15, h + ah / 2 + 0.03))   # incl. sleeve
    # tube housing + collimator around the focal spot
    head = Rect(cx - hl / 2 - 0.03, f_off - hr, cx + hl / 2 + 0.03, f_off + collimator_front(t_cfg))
    boxes.append(_box(transform_rect(head, ox, oy, yaw), h - max(hr, ch / 2) - 0.05, h + max(hr, ch / 2)))
    return np.array(boxes, dtype=float).reshape(-1, 6)


# --- camera geometry -------------------------------------------------------------------------------------------
def basis(forward):
    f = np.asarray(forward, float)
    f = f / np.linalg.norm(f)
    up = np.array([0.0, 0.0, 1.0]) if abs(f[2]) < 0.999 else np.array([0.0, 1.0, 0.0])
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    return f, r, np.cross(r, f)


def in_frame(eye, forward, points, tan_h, tan_v, near=0.05):
    f, r, u = basis(forward)
    d = points - eye
    z = d @ f
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = (z > near) & (np.abs((d @ r) / z) <= tan_h) & (np.abs((d @ u) / z) <= tan_v)
    return ok


def unoccluded(eye, points, boxes):
    """True where the segment eye -> point does not pass through any box (slab test)."""
    if len(points) == 0 or len(boxes) == 0:
        return np.ones(len(points), dtype=bool)
    d = points - eye                                           # (N, 3)
    d = np.where(np.abs(d) < 1e-9, 1e-9, d)
    lo, hi = boxes[:, None, :3], boxes[:, None, 3:]            # (M, 1, 3)
    t0, t1 = (lo - eye) / d[None], (hi - eye) / d[None]        # (M, N, 3)
    tmin = np.minimum(t0, t1).max(axis=2)
    tmax = np.maximum(t0, t1).min(axis=2)
    hit = (tmax >= np.maximum(tmin, 1e-6)) & (tmin < 1.0 - 1e-4)
    return ~hit.any(axis=0)


def visibility(eye, forward, tan_h, tan_v, groups, boxes, occlusion=True):
    out = {}
    for name, pts in groups.items():
        if len(pts) == 0:
            out[name] = np.zeros(0, dtype=bool)
            continue
        vis = in_frame(eye, forward, pts, tan_h, tan_v)
        if occlusion:
            vis &= unoccluded(eye, pts, boxes)
        out[name] = vis
    return out


def score(vis, weights):
    total = sum(weights[g] for g, v in vis.items() if len(v))
    return sum(weights[g] * v.mean() for g, v in vis.items() if len(v)) / (total or 1.0)


def fit_view(eye, points, ha, va, focal_range, margin, iterations=5):
    """Aim at the angular centre of `points` and pick the longest focal length that still frames them all
    (clamped to focal_range). Returns (forward, focal_mm)."""
    eye = np.asarray(eye, float)
    dirs = points - eye
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    fwd = dirs.mean(axis=0)
    for _ in range(iterations):
        f, r, u = basis(fwd)
        d = points - eye
        z = np.maximum(d @ f, 1e-3)
        tx, ty = (d @ r) / z, (d @ u) / z
        cx, cy = (tx.max() + tx.min()) / 2, (ty.max() + ty.min()) / 2
        fwd = f + cx * r + cy * u
    f, r, u = basis(fwd)
    d = points - eye
    front = (d @ f) > 1e-3
    z = np.maximum(d @ f, 1e-3)
    ex = np.abs((d @ r) / z)[front].max(initial=1e-3) * (1 + margin)
    ey = np.abs((d @ u) / z)[front].max(initial=1e-3) * (1 + margin)
    focal = min(ha / (2 * ex), va / (2 * ey))
    return f, float(min(max(focal, focal_range[0]), focal_range[1]))


def best_view(eye, groups, boxes, ha, va, cov):
    """Best aim + lens at one mount: fit to everything, or to the patient groups only, whichever scores higher."""
    weights, frng, margin = cov["weights"], cov["focal_length_mm"], cov["margin"]
    patient = [g for g in ("marker", "walk_path", "walk_feet", "support") if len(groups[g])]
    best = None
    for subset in (list(GROUPS), patient, ["marker", "walk_path"]):
        pts = np.concatenate([groups[g] for g in subset if len(groups[g])])
        fwd, focal = fit_view(eye, pts, ha, va, frng, margin)
        tan_h, tan_v = ha / (2 * focal), va / (2 * focal)
        vis = visibility(np.asarray(eye, float), fwd, tan_h, tan_v, groups, boxes, cov.get("occlusion", True))
        s = score(vis, weights)
        if best is None or s > best[0] + 1e-9:
            best = (s, fwd, focal, vis)
    return best
