"""Build the anatomical skeleton for one human: one skinned mesh per bone, parented to the rig."""

import logging

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .. import bake, colors, geometry, preview
from ..gown.profile import is_profile_bone
from ..gown.regions import dominant_bones
from . import appendicular, axial

_LOG = logging.getLogger("sdg_humans.blender.anatomy")

PARTS = {
    "skull": axial.skull, "vertebrae": axial.vertebrae, "ribs": axial.ribs, "sternum": axial.sternum,
    "shoulder_girdle": appendicular.shoulder_girdle, "pelvis": appendicular.pelvis,
    "limbs": appendicular.limbs, "hands_feet": appendicular.hands_feet,
}


def _context(basemesh, armature, landmarks: dict, levels: list, stature_m: float, cfg: dict) -> dict:
    coords = geometry.evaluated_coords(basemesh)
    body = geometry.group_vertex_indices(basemesh, "body")
    dom = dominant_bones(basemesh, {b.name for b in armature.data.bones})
    keep = {i for i in body if is_profile_bone(dom.get(i)) or str(dom.get(i)).startswith("neck")}
    polys = [list(p.vertices) for p in basemesh.data.polygons if all(v in keep for v in p.vertices)]
    bvh = BVHTree.FromPolygons([tuple(c) for c in coords], polys)
    midline = [coords[i] for i in body if abs(coords[i].x) < 0.01]
    s = stature_m / 1.70
    world = armature.matrix_world
    bones = armature.data.bones

    def front_y_at(z):
        ys = [c.y for c in midline if abs(c.z - z) < 0.012]
        return min(ys) if ys else -0.1

    def back_point(x, z):
        origin = Vector((x, front_y_at(z) + 0.04, z))
        hit = bvh.ray_cast(origin, Vector((0, 1, 0)), 1.0)[0]
        return hit - Vector((0, 1, 0)) * max(float(cfg["soft_tissue_cm"]) / 100.0 * s, 0.01) if hit else None

    return {
        "cfg": cfg, "s": s, "levels": levels, "bones": [b.name for b in bones],
        "lm": {name: Vector(info["rest_position_m"]) for name, info in landmarks.items()},
        "lm_parent": {name: info["parent"] for name, info in landmarks.items()},
        "head": lambda n: world @ bones[n].head_local, "tail": lambda n: world @ bones[n].tail_local,
        "lateral": lambda n: (world.to_3x3() @ bones[n].matrix_local.to_3x3().col[0]).normalized(),
        "torso_bvh": bvh, "front_y_at": front_y_at, "back_point": back_point,
        "soft_tissue_m": float(cfg["soft_tissue_cm"]) / 100.0 * s,
        "soft_tissue_fraction": float(cfg.get("soft_tissue_fraction", 0.08)),
    }


def keep_inside(obj, body_bvh, margin_m: float) -> int:
    """Pull every bone vertex at least margin_m inside the skin (no bone ever shows through).
    Vertices are in world space (the bone object has an identity world matrix)."""
    moved = 0
    for vertex in obj.data.vertices:
        p = vertex.co.copy()
        loc, normal, _i, dist = body_bvh.find_nearest(p)
        if loc is None:
            continue
        outside = (p - loc).dot(normal) > 0
        if outside or dist < margin_m:
            p = loc - normal * margin_m
            moved += 1
        vertex.co = p
    obj.data.update()
    return moved


HEAD_BONES = ("skull", "mandible")


def head_occluders(basemesh, armature, landmarks: dict):
    """BVH of the head skin plus the eyeballs (the skin is open at the eyes, mouth and nostrils) and
    the head centre (between the tragi, 1.5 cm forward)."""
    coords = geometry.evaluated_coords(basemesh)
    body = set(geometry.group_vertex_indices(basemesh, "body"))
    verts = [tuple(c) for c in coords]
    polys = [list(p.vertices) for p in basemesh.data.polygons if all(v in body for v in p.vertices)]
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in armature.children_recursive:
        name = obj.name.lower()
        if obj.type != "MESH" or "eye" not in name or "brow" in name or "lash" in name:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        offset = len(verts)
        verts += [tuple(evaluated.matrix_world @ v.co) for v in mesh.vertices]
        polys += [[offset + i for i in p.vertices] for p in mesh.polygons]
        evaluated.to_mesh_clear()
    tl, tr = Vector(landmarks["tragus_L"]["rest_position_m"]), Vector(landmarks["tragus_R"]["rest_position_m"])
    centre = (tl + tr) / 2 + Vector((0.0, -0.015, 0.0))
    return BVHTree.FromPolygons(verts, polys), centre


def clamp_radial(obj, bvh, centre, margin_m: float, fallback: float = 0.8) -> int:
    """Keep every vertex margin_m inside the first skin / eyeball surface hit by a ray from the head
    centre through it. A ray escaping through the mouth or a nostril pulls the vertex to `fallback`
    of its distance."""
    moved = 0
    for vertex in obj.data.vertices:
        offset = vertex.co - centre
        length = offset.length
        if length < 1e-6:
            continue
        direction = offset / length
        hit = bvh.ray_cast(centre, direction, 0.4)[0]
        allowed = ((hit - centre).length - margin_m) if hit is not None else length * fallback
        if length > allowed:
            vertex.co = centre + direction * max(allowed, 0.0)
            moved += 1
    obj.data.update()
    return moved


def refine(obj, max_edge_m: float, passes: int = 3) -> None:
    """Split long edges so no bone triangle can span a skin concavity (nostrils, eye-cheek crease)
    while all its corners are inside. Vertex-group weights are interpolated by bmesh."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for _ in range(passes):
        long_edges = [e for e in bm.edges if e.calc_length() > max_edge_m]
        if not long_edges:
            break
        bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(obj.data)
    bm.free()


def build_skeleton(basemesh, armature, landmarks: dict, levels: list, stature_m: float, cfg: dict,
                   human_id: str) -> list:
    """Returns metadata entries [{name, object, rig_bone, vertices}] for every bone mesh."""
    ctx = _context(basemesh, armature, landmarks, levels, stature_m, cfg)
    material = bake.simple_material(f"{human_id}_bone", color=colors.hex_to_linear_rgba(cfg.get("color_rgb", "#e3d8c3")),
                                    roughness=0.6)
    coords = geometry.evaluated_coords(basemesh)
    body = set(geometry.group_vertex_indices(basemesh, "body"))
    body_bvh = BVHTree.FromPolygons([tuple(c) for c in coords], [list(p.vertices) for p in basemesh.data.polygons
                                                                 if all(v in body for v in p.vertices)])
    margin = float(cfg.get("min_depth_below_skin_cm", 0.4)) / 100.0
    max_edge = float(cfg.get("max_edge_cm", 1.0)) / 100.0
    head_margin = float(cfg.get("head_depth_below_skin_cm", 0.8)) / 100.0
    head_bvh, head_centre = head_occluders(basemesh, armature, landmarks)
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
            obj = acc.to_object(f"bone_{name}", material, armature)
            refine(obj, max_edge * (0.5 if name in HEAD_BONES else 1.0))   # face creases need finer skull faces
            pulled = keep_inside(obj, body_bvh, margin)
            if name in HEAD_BONES:
                pulled += clamp_radial(obj, head_bvh, head_centre, head_margin)
            if pulled:
                _LOG.debug(f"bone {name}: {pulled} of {len(obj.data.vertices)} vertices pulled inside the skin")
            if thickness:
                solid = obj.modifiers.new("BoneThickness", "SOLIDIFY")
                solid.thickness, solid.offset = thickness, 0.0
            created.append({"name": name, "object": obj.name, "rig_bone": rig_bone, "part": part,
                            "vertices": len(obj.data.vertices)})
    _LOG.info(f"anatomical skeleton: {len(created)} bone meshes")
    return created


def render_skeleton_preview(path, stature_m: float, preview_cfg: dict, bone_objects: list) -> None:
    """Front + side render of the bone meshes only (other meshes hidden for the render)."""
    names = {entry["object"] for entry in bone_objects}
    hidden = []
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.name not in names and not obj.hide_render:
            obj.hide_render = True
            hidden.append(obj)
    try:
        preview.render_preview(path, stature_m, preview_cfg)
    finally:
        for obj in hidden:
            obj.hide_render = False
