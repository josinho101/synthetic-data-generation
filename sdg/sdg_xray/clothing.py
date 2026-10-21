"""Hide the body skin that lies under clothing, so it cannot poke through the garments in poses (pxr + numpy).

The synthetic humans keep the complete body mesh under their clothes. Body and garments are skinned to the same
skeleton but with different weights, so in raised-arm or hands-on-hip poses the skin pushes through close-fitting
cloth (skin-coloured "gaps" in the shirt). MakeHuman solves this with delete groups; here the covered faces are found
geometrically on the rest pose and removed from the body mesh in the in-memory stage:

  * a body vertex is *covered* when a short ray along its outward normal hits a garment triangle within
    `max_dist_m` (cloth sits a few mm to cm outside the skin), or the garment surface is just inside it (`inside_m`);
  * a body face is removed only when all its vertices are covered, so skin at hems, collars and sleeve ends stays.
"""

import re
from collections import defaultdict

import numpy as np
from pxr import Usd, UsdGeom, Vt

BODY_MESH_NAME = "base"


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def _world_points(prim) -> np.ndarray:
    mesh = UsdGeom.Mesh(prim)
    pts = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
    m = np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=np.float64)
    return pts @ m[:3, :3] + m[3, :3]


def _triangles(counts, indices) -> np.ndarray:
    """Fan triangulation -> (T, 3) vertex indices, and the polygon each triangle came from."""
    tris, owner, k = [], [], 0
    for f, n in enumerate(counts):
        for j in range(1, n - 1):
            tris.append((indices[k], indices[k + j], indices[k + j + 1]))
            owner.append(f)
        k += n
    return np.asarray(tris, dtype=np.int64), np.asarray(owner, dtype=np.int64)


def _vertex_normals(points, tris) -> np.ndarray:
    a, b, c = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    vn = np.zeros_like(points)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    length = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.where(length > 1e-12, length, 1.0)


def covered_vertices(body_pts, body_normals, garment_tris_xyz, max_dist_m=0.07, inside_m=0.006, cell_m=0.05):
    """Boolean mask of body vertices whose outward normal ray hits a garment triangle in [-inside_m, max_dist_m]."""
    covered = np.zeros(len(body_pts), dtype=bool)
    if len(garment_tris_xyz) == 0:
        return covered
    lo = np.minimum(np.minimum(garment_tris_xyz[:, 0], garment_tris_xyz[:, 1]), garment_tris_xyz[:, 2])
    hi = np.maximum(np.maximum(garment_tris_xyz[:, 0], garment_tris_xyz[:, 1]), garment_tris_xyz[:, 2])
    grid = defaultdict(list)
    for t, (l, h) in enumerate(zip(np.floor(lo / cell_m).astype(int), np.floor(hi / cell_m).astype(int))):
        for i in range(l[0], h[0] + 1):
            for j in range(l[1], h[1] + 1):
                for k in range(l[2], h[2] + 1):
                    grid[(i, j, k)].append(t)
    reach = max_dist_m + inside_m
    for v, (p, n) in enumerate(zip(body_pts, body_normals)):
        cells = set()                                           # every grid cell the ray passes through
        steps = max(2, int(np.ceil(reach / (cell_m * 0.5))) + 1)
        for s in np.linspace(-inside_m, max_dist_m, steps):
            c = np.floor((p + n * s) / cell_m).astype(int)
            cells.add((c[0], c[1], c[2]))
        cand = sorted({t for c in cells for t in grid.get(c, ())})
        if not cand:
            continue
        tri = garment_tris_xyz[cand]
        origin = p - n * inside_m                               # Moller-Trumbore, ray origin just inside the skin
        e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
        pvec = np.cross(n, e2)
        det = np.einsum("ij,ij->i", e1, pvec)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tvec = origin - tri[:, 0]
        u = np.einsum("ij,ij->i", tvec, pvec) * inv
        qvec = np.cross(tvec, e1)
        w = (qvec @ n) * inv
        dist = np.einsum("ij,ij->i", e2, qvec) * inv
        hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (dist >= 0) & (dist <= reach)
        covered[v] = bool(hit.any())
    return covered


def remove_faces(mesh_prim, keep_face: np.ndarray) -> int:
    """Drop faces (keep_face False) from a mesh, with its face-varying and uniform primvars. Returns faces removed."""
    mesh = UsdGeom.Mesh(mesh_prim)
    counts = list(mesh.GetFaceVertexCountsAttr().Get())
    indices = list(mesh.GetFaceVertexIndicesAttr().Get())
    keep_fv, start = [], 0
    for f, n in enumerate(counts):
        keep_fv.extend([bool(keep_face[f])] * n)
        start += n
    keep_fv = np.asarray(keep_fv, dtype=bool)
    mesh.GetFaceVertexCountsAttr().Set(Vt.IntArray([c for c, k in zip(counts, keep_face) if k]))
    mesh.GetFaceVertexIndicesAttr().Set(Vt.IntArray([i for i, k in zip(indices, keep_fv) if k]))
    for pv in UsdGeom.PrimvarsAPI(mesh_prim).GetPrimvars():
        interp = pv.GetInterpolation()
        mask = keep_fv if interp == UsdGeom.Tokens.faceVarying else keep_face if interp == UsdGeom.Tokens.uniform else None
        if mask is None:
            continue
        if pv.IsIndexed():
            idx = pv.GetIndicesAttr().Get()
            if idx is not None and len(idx) == len(mask):
                pv.GetIndicesAttr().Set(Vt.IntArray([i for i, k in zip(idx, mask) if k]))
        else:
            val = pv.Get()
            if val is not None and len(val) == len(mask):
                pv.Set(type(val)([x for x, k in zip(val, mask) if k]))
    normals = mesh.GetNormalsAttr()
    if normals.HasAuthoredValue():
        val = normals.Get()
        mask = keep_fv if mesh.GetNormalsInterpolation() == UsdGeom.Tokens.faceVarying else \
            keep_face if mesh.GetNormalsInterpolation() == UsdGeom.Tokens.uniform else None
        if mask is not None and val is not None and len(val) == len(mask):
            normals.Set(type(val)([x for x, k in zip(val, mask) if k]))
    return int((~keep_face).sum())


def hide_body_under_clothes(skelroot, garment_names, max_dist_m=0.07, inside_m=0.006) -> dict:
    """Find the body mesh and the garment meshes (by clothing item name) below `skelroot` and remove the covered
    body faces. Returns {"garments": [...], "removed": n, "faces": total}."""
    body, garments = None, []
    wanted = [sanitize(n).lower() for n in garment_names]
    for prim in Usd.PrimRange(skelroot):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        if prim.GetName() == BODY_MESH_NAME:
            body = prim
        elif any(w and w in prim.GetParent().GetName().lower() for w in wanted):
            garments.append(prim)
    if body is None or not garments:
        return {"garments": [g.GetParent().GetName() for g in garments], "removed": 0, "faces": 0}
    bmesh = UsdGeom.Mesh(body)
    counts = list(bmesh.GetFaceVertexCountsAttr().Get())
    indices = list(bmesh.GetFaceVertexIndicesAttr().Get())
    bpts = _world_points(body)
    btris, _ = _triangles(counts, indices)
    normals = _vertex_normals(bpts, btris)
    gtris = []
    for g in garments:
        gm = UsdGeom.Mesh(g)
        tris, _ = _triangles(list(gm.GetFaceVertexCountsAttr().Get()), list(gm.GetFaceVertexIndicesAttr().Get()))
        gtris.append(_world_points(g)[tris])
    covered = covered_vertices(bpts, normals, np.concatenate(gtris), max_dist_m, inside_m)
    keep, k = np.ones(len(counts), dtype=bool), 0
    for f, n in enumerate(counts):
        keep[f] = not covered[indices[k:k + n]].all()
        k += n
    removed = remove_faces(body, keep)
    return {"garments": [g.GetParent().GetName() for g in garments], "removed": removed, "faces": len(counts)}
