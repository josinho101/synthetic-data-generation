"""Remove skin poke-through: push garment vertices that lie inside (or too close to) the body out.

MHCLO fitting follows each body only approximately; on full bodies the skin pokes through tight
garments (breasts through a t-shirt, thighs through a skirt). The body is kept complete (it is
needed for landmarks, bone meshes and segmentation), so the garments are corrected instead:
modifiers are applied first (thickness, smoothing, layer offset), then every vertex closer than
the clearance to the skin is moved out along the skin normal.
"""

import logging

import bpy
from mathutils.bvhtree import BVHTree

from . import geometry

_LOG = logging.getLogger("sdg_humans.blender.garment_fit")


def body_bvh(basemesh):
    coords = geometry.evaluated_coords(basemesh)
    body = set(geometry.group_vertex_indices(basemesh, "body"))
    polys = [list(p.vertices) for p in basemesh.data.polygons if all(v in body for v in p.vertices)]
    return BVHTree.FromPolygons([tuple(c) for c in coords], polys)


def _apply_modifiers(obj) -> None:
    for obj_sel in bpy.context.view_layer.objects:
        obj_sel.select_set(obj_sel == obj)
    bpy.context.view_layer.objects.active = obj
    for modifier in list(obj.modifiers):
        if modifier.type != "ARMATURE":
            bpy.ops.object.modifier_apply(modifier=modifier.name)


def refine_near_body(obj, bvh, max_edge_m: float, near_m: float, passes: int = 2) -> int:
    """Split long garment edges close to the skin, so that faces cannot cut through a curved body
    part (e.g. the chest) while their corners are outside. UVs and weights are interpolated."""
    import bmesh
    to_world = obj.matrix_world
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    added = 0
    for _ in range(passes):
        near = {v for v in bm.verts if (hit := bvh.find_nearest(to_world @ v.co, near_m))[0] is not None}
        edges = [e for e in bm.edges if e.calc_length() * to_world.median_scale > max_edge_m
                 and (e.verts[0] in near or e.verts[1] in near)]
        if not edges:
            break
        before = len(bm.verts)
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        added += len(bm.verts) - before
    bm.to_mesh(obj.data)
    bm.free()
    return added


def push_out(obj, bvh, clearance_m: float, max_edge_m: float = 0.012, max_dist_m: float = 0.06) -> int:
    """Move vertices within clearance of (or inside) the skin to clearance outside it."""
    _apply_modifiers(obj)
    if max_edge_m > 0:
        refine_near_body(obj, bvh, max_edge_m, near_m=clearance_m + 0.01)
    to_world, to_local = obj.matrix_world, obj.matrix_world.inverted()
    moved = 0
    for vertex in obj.data.vertices:
        p = to_world @ vertex.co
        loc, normal, _i, dist = bvh.find_nearest(p, max_dist_m)
        if loc is None:
            continue
        if (p - loc).dot(normal) < clearance_m:
            vertex.co = to_local @ (loc + normal * clearance_m)
            moved += 1
    obj.data.update()
    return moved


def resolve_poke_through(basemesh, worn: list, clothing: dict) -> None:
    clearance = float(clothing.get("poke_through_clearance_cm", 0.3)) / 100.0
    if clearance <= 0:
        return
    offset = float(clothing.get("layer_offset_cm", 0.5)) / 100.0
    skip = set(clothing.get("hide_body_under") or [])
    bvh = body_bvh(basemesh)
    for item in sorted(worn, key=lambda w: w.get("layer") == "outer"):   # inner garments first
        if item["slot"] in skip:
            continue
        obj = bpy.data.objects[item["object"]]
        extra = offset if item.get("layer") == "outer" else 0.0
        moved = push_out(obj, bvh, clearance + extra, float(clothing.get("poke_through_max_edge_cm", 1.2)) / 100.0)
        item["poke_through_fixed_vertices"] = moved
        _LOG.info(f"poke-through: {item['asset']} {moved} vertices pushed out of the body")
