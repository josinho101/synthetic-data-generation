"""Save the closed body for a host-side skeletal layer (sdg_humans/skeleton, e.g. 'zanatomy').

The exported body loses faces under clothes (holes) and sometimes vertices under shoes, so the layer gets the full
MakeHuman body instead: the basemesh evaluated in world space (after the floor lift, i.e. in the exported USD's
space) with helper geometry removed exactly as the Z-Anatomy reference skin was made, so vertex i is MakeHuman
body vertex i (13 380 vertices).
"""

import logging

import numpy as np

_LOG = logging.getLogger("sdg_humans.blender.skeleton_dump")
HELPER_GROUPS = ("HelperGeometry", "JointCubes")


def dump_body(basemesh, path, fit_result: dict, spec: dict) -> dict:
    import bpy

    masks = [m for m in basemesh.modifiers if m.type == "MASK"]
    states = [(m, m.show_viewport) for m in masks]
    for m in masks:
        m.show_viewport = False
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        ev = basemesh.evaluated_get(dg)
        me = ev.to_mesh()
        n = len(me.vertices)
        if n != len(basemesh.data.vertices):
            raise RuntimeError(f"evaluated basemesh has {n} vertices, expected {len(basemesh.data.vertices)}")
        co = np.empty(n * 3)
        me.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world)
        co = co.reshape(n, 3) @ M[:3, :3].T + M[:3, 3]
        polys = [list(p.vertices) for p in me.polygons]
        ev.to_mesh_clear()
    finally:
        for m, state in states:
            m.show_viewport = state
    helpers = {g.index for g in basemesh.vertex_groups if g.name in HELPER_GROUPS}
    keep = np.ones(n, dtype=bool)
    for v in basemesh.data.vertices:
        if any(g.group in helpers and g.weight > 0.5 for g in v.groups):
            keep[v.index] = False
    remap = -np.ones(n, dtype=np.int64)
    remap[keep] = np.arange(int(keep.sum()))
    tris = []
    for p in polys:
        if all(keep[i] for i in p):
            q = [int(remap[i]) for i in p]
            tris += [[q[0], q[k], q[k + 1]] for k in range(1, len(q) - 1)]
    np.savez(path, vertices=co[keep].astype(np.float64), triangles=np.array(tris, dtype=np.int64),
             bmi=float(fit_result["bmi"]), height_cm=float(fit_result["height_cm"]),
             weight_kg=float(fit_result["weight_kg"]), sex=str(spec["sex"]))
    _LOG.info(f"closed body for the skeletal layer: {int(keep.sum())} vertices, {len(tris)} triangles -> {path}")
    return {"path": str(path), "vertices": int(keep.sum()), "triangles": len(tris)}
