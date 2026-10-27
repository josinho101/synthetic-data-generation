"""Build the anatomical skeleton for one human: one rigidly skinned mesh per bone (port of the MPFB version)."""

import logging

import numpy as np

from ..geometry import MeshBVH, RadialDepth, Vector, triangulate
from . import appendicular, axial
from .prims import solidify, subdivide

_LOG = logging.getLogger("anny_humans.anatomy")

PARTS = {
    "skull": axial.skull, "vertebrae": axial.vertebrae, "ribs": axial.ribs, "sternum": axial.sternum,
    "shoulder_girdle": appendicular.shoulder_girdle, "pelvis": appendicular.pelvis,
    "limbs": appendicular.limbs, "hands_feet": appendicular.hands_feet,
}

TORSO = {"root", "spine01", "spine02", "spine03", "spine04", "spine05", "breast.L", "breast.R",
         "pelvis.L", "pelvis.R", "clavicle.L", "clavicle.R", "shoulder01.L", "shoulder01.R"}
LEG_PREFIXES = ("upperleg", "lowerleg")
HEAD_BONES = ("skull", "mandible")


def _is_profile_bone(name) -> bool:
    return bool(name) and (name in TORSO or name.startswith(LEG_PREFIXES))


def _context(body, rest, landmarks: dict, levels: list, stature_m: float, cfg: dict) -> dict:
    coords = rest.vertices
    idx = body.body_vertices
    dominant = body.dominant_bones()
    keep = np.zeros(body.vertex_count, dtype=bool)
    for i in idx:
        name = body.bone_labels[int(dominant[i])]
        keep[i] = _is_profile_bone(name) or name.startswith("neck")
    faces = body.faces[body.body_faces]
    torso_faces = faces[np.all(keep[np.clip(faces, 0, None)] | (faces < 0), axis=1)]
    bvh = MeshBVH(coords, triangulate(torso_faces))
    midline = coords[idx][np.abs(coords[idx, 0]) < 0.01]
    s = stature_m / 1.70
    index = {n: i for i, n in enumerate(body.bone_labels)}

    def front_y_at(z):
        ys = midline[np.abs(midline[:, 2] - z) < 0.012, 1]
        return float(ys.min()) if len(ys) else -0.1

    def back_point(x, z):
        origin = Vector((x, front_y_at(z) + 0.04, z))
        hit = bvh.ray_cast(origin, Vector((0, 1, 0)), 1.0)[0]
        return hit - Vector((0, 1, 0)) * max(float(cfg["soft_tissue_cm"]) / 100.0 * s, 0.01) if hit else None

    return {
        "cfg": cfg, "s": s, "levels": levels, "bones": list(body.bone_labels),
        "lm": {name: Vector(info["rest_position_m"]) for name, info in landmarks.items()},
        "lm_parent": {name: info["parent"] for name, info in landmarks.items()},
        "head": lambda n: Vector(rest.heads[index[n]]), "tail": lambda n: Vector(rest.tails[index[n]]),
        "lateral": lambda n: Vector(rest.world[index[n]][:3, 0]).normalized(),
        "torso_bvh": bvh, "front_y_at": front_y_at, "back_point": back_point,
        "soft_tissue_m": float(cfg["soft_tissue_cm"]) / 100.0 * s,
        "soft_tissue_fraction": float(cfg.get("soft_tissue_fraction", 0.08)),
    }


def keep_inside(points, body_bvh: MeshBVH, margin_m: float) -> tuple:
    """Pull every bone vertex at least margin_m inside the skin (no bone ever shows through)."""
    loc, normal, outside, dist = body_bvh.signed_distance_out(points)
    move = (outside > 0) | (dist < margin_m)
    points = points.copy()
    points[move] = loc[move] - normal[move] * margin_m
    return points, int(move.sum())


def clamp_radial(points, depth: RadialDepth, margin_m: float, fallback: float = 0.8) -> tuple:
    """Keep every vertex margin_m inside the first skin / eyeball surface hit by a ray from the head centre through
    it. A ray escaping through the mouth or a nostril pulls the vertex to `fallback` of its distance."""
    offsets = points - depth.centre
    lengths = np.linalg.norm(offsets, axis=1)
    hits = depth.first_hit(points, 0.4)
    allowed = np.where(np.isfinite(hits), hits - margin_m, lengths * fallback)
    move = (lengths > 1e-6) & (lengths > allowed)
    points = points.copy()
    points[move] = depth.centre + offsets[move] / lengths[move, None] * np.maximum(allowed[move], 0.0)[:, None]
    return points, int(move.sum())


def build_skeleton(body, rest, landmarks: dict, levels: list, stature_m: float, cfg: dict,
                   eye_meshes=()) -> list:
    """-> [{name, rig_bone, part, points, tris, weights}] for every bone mesh (USD space).
    eye_meshes: [(points, tris)] of the eyeballs (the head skin is open at the eyes)."""
    ctx = _context(body, rest, landmarks, levels, stature_m, cfg)
    body_tris = body.triangles(body.body_faces)
    body_bvh = MeshBVH(rest.vertices, body_tris)
    tl, tr = np.array(landmarks["tragus_L"]["rest_position_m"]), np.array(landmarks["tragus_R"]["rest_position_m"])
    head_centre = (tl + tr) / 2 + np.array([0.0, -0.015, 0.0])
    near = np.linalg.norm(rest.vertices - head_centre, axis=1) < 0.25     # head skin only
    verts, tris = [rest.vertices], [body_tris[near[body_tris].all(1)]]
    offset = len(rest.vertices)
    for points, eye_tris in eye_meshes:
        verts.append(points)
        tris.append(np.asarray(eye_tris) + offset)
        offset += len(points)
    head_depth = RadialDepth(np.concatenate(verts), np.concatenate(tris), head_centre)
    margin = float(cfg.get("min_depth_below_skin_cm", 0.4)) / 100.0
    max_edge = float(cfg.get("max_edge_cm", 1.0)) / 100.0
    head_margin = float(cfg.get("head_depth_below_skin_cm", 0.8)) / 100.0
    created = []
    for part in cfg.get("parts", list(PARTS)):
        try:
            pieces = PARTS[part](ctx)
        except (KeyError, ValueError) as exc:
            _LOG.warning(f"anatomy part {part} skipped: {exc}")
            continue
        for name, piece in pieces.items():
            acc, rig_bone = piece[0], piece[1]
            thickness = piece[2] if len(piece) > 2 else None
            if not acc.faces:
                continue
            points, faces, weights = acc.arrays()
            points, faces, weights = subdivide(points, faces, weights,       # face creases need finer skull faces
                                               max_edge * (0.5 if name in HEAD_BONES else 1.0))
            points, pulled = keep_inside(points, body_bvh, margin)
            if name in HEAD_BONES:
                points, more = clamp_radial(points, head_depth, head_margin)
                pulled += more
            if pulled:
                _LOG.debug(f"bone {name}: {pulled} of {len(points)} vertices pulled inside the skin")
            if thickness:
                points, faces, weights = solidify(points, faces, weights, thickness)
            created.append({"name": name, "rig_bone": rig_bone, "part": part, "points": points, "tris": faces,
                            "weights": weights})
    _LOG.info(f"anatomical skeleton: {len(created)} bone meshes")
    return created
