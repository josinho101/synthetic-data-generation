"""Geometry helpers on the evaluated (shape-keyed) basemesh, in world space (meters)."""

import bmesh
import bpy
from mathutils import Vector


def group_vertex_indices(obj, group_name: str) -> list:
    group = obj.vertex_groups.get(group_name)
    if group is None:
        return []
    gi = group.index
    return [v.index for v in obj.data.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups)]


def evaluated_coords(obj) -> list:
    """World coordinates of ALL basemesh vertices (original indices), shape keys applied."""
    states = [(m, m.show_viewport) for m in obj.modifiers]
    for modifier, _ in states:
        modifier.show_viewport = False
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        matrix = obj.matrix_world
        coords = [matrix @ v.co for v in mesh.vertices]
        evaluated.to_mesh_clear()
    finally:
        for modifier, shown in states:
            modifier.show_viewport = shown
    return coords


def joint_centre(obj, coords: list, joint_group: str) -> Vector:
    """Centre of one MPFB joint-cube vertex group (e.g. 'joint-neck')."""
    indices = group_vertex_indices(obj, joint_group)
    if not indices:
        raise KeyError(f"vertex group {joint_group} not found on basemesh")
    total = Vector((0.0, 0.0, 0.0))
    for i in indices:
        total += coords[i]
    return total / len(indices)


def body_extent(coords: list, body_indices: list) -> tuple:
    zs = [coords[i].z for i in body_indices]
    return min(zs), max(zs)


def body_volume_m3(obj, coords: list, body_indices: list) -> float:
    """Volume of the body surface (helpers excluded) via bmesh.calc_volume."""
    keep = set(body_indices)
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        for v in bm.verts:
            v.co = coords[v.index]
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context="VERTS")
        return abs(bm.calc_volume(signed=True))
    finally:
        bm.free()


def strip_layers(bm) -> None:
    """Drop vertex-group weights and shape-key layers copied from the basemesh."""
    for layer in list(bm.verts.layers.deform.values()):
        bm.verts.layers.deform.remove(layer)
    for layer in list(bm.verts.layers.shape.values()):
        bm.verts.layers.shape.remove(layer)


def body_volume_columns_m3(obj, coords: list, body_indices: list, cell_m: float = 0.01) -> float:
    """Robust volume: cast vertical rays on an XY grid and integrate inside-lengths (hit parity).

    Insensitive to small holes (eye sockets, mouth) that bias bmesh.calc_volume.
    """
    from mathutils.bvhtree import BVHTree

    keep = set(body_indices)
    polys = [list(p.vertices) for p in obj.data.polygons if all(v in keep for v in p.vertices)]
    bvh = BVHTree.FromPolygons([tuple(c) for c in coords], polys)
    xs = [coords[i].x for i in body_indices]
    ys = [coords[i].y for i in body_indices]
    z0 = min(coords[i].z for i in body_indices) - 0.01
    up = Vector((0.0, 0.0, 1.0))
    total = 0.0
    nx, ny = int((max(xs) - min(xs)) / cell_m) + 1, int((max(ys) - min(ys)) / cell_m) + 1
    for ix in range(nx):
        for iy in range(ny):
            origin = Vector((min(xs) + (ix + 0.5) * cell_m, min(ys) + (iy + 0.5) * cell_m, z0))
            hits = []
            while True:
                loc, _n, _i, dist = bvh.ray_cast(origin, up, 3.0)
                if loc is None:
                    break
                hits.append(loc.z)
                origin = loc + up * 1e-4
            for a, b in zip(hits[0::2], hits[1::2]):
                total += (b - a)
    return total * cell_m * cell_m
