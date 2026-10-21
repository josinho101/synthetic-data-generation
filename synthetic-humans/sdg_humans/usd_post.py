"""Post-export fixes on a human USD (usd-core / pxr + numpy), applied after the Blender build, before validation.

export.yaml -> usd_post:
  * root_joint       : insert an identity root joint above MPFB's `root` (which sits at the pelvis). Retargeters
                       (e.g. Isaac Sim's omni.anim.retarget) need the hips below a root at the origin. The name must
                       not equal "root" ignoring case.
  * anatomy_purpose  : UsdGeom purpose of the `bone_*` anatomical skeleton meshes. "guide" keeps them in the file
                       but out of renders: they are skinned rigidly, so in strong poses they poke through the skin.
  * clothing_holes   : body faces fully covered by a garment become `holeIndices` of the body mesh: not rendered,
                       so skin cannot poke through the clothes in poses (body and garments are skinned with
                       different weights). Points and topology stay complete for measurements and landmarks.
"""

import re
from collections import defaultdict

import numpy as np

BODY_MESH_NAME = "base"


# ----------------------------------------------------------------------------------------------- root joint
def add_root_joint(stage, name: str) -> bool:
    from pxr import Gf, Usd, UsdGeom, UsdSkel

    if not name:
        return False
    if name.lower() == "root":
        raise ValueError("usd_post.root_joint must differ from MPFB's 'root' (case-insensitive)")
    skel_prim = next((p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton)), None)
    root_prim = next((p for p in stage.Traverse() if p.IsA(UsdSkel.Root)), None)
    if skel_prim is None:
        return False
    skel = UsdSkel.Skeleton(skel_prim)
    joints = list(skel.GetJointsAttr().Get())
    if joints[0] == name:
        return False
    skel.GetJointsAttr().Set([name] + [f"{name}/{j}" for j in joints])
    for attr in (skel.GetBindTransformsAttr(), skel.GetRestTransformsAttr()):
        if attr.HasAuthoredValue():
            attr.Set([Gf.Matrix4d(1.0)] + list(attr.Get()))
    names = skel.GetJointNamesAttr()
    if names.HasAuthoredValue() and names.Get() and len(names.Get()) == len(joints):
        names.Set([name] + list(names.Get()))
    for attr in skel_prim.GetAttributes():           # per-joint primvars (e.g. blender:bone_lengths)
        value = attr.Get()
        if attr.GetName().startswith("primvars:") and value is not None and hasattr(value, "__len__") \
                and not isinstance(value, str) and len(value) == len(joints):
            first = 0.1 if isinstance(value[0], float) else value[0]       # bone length of the new root: 0.1 m
            attr.Set(type(value)([first] + list(value)))
    for prim in Usd.PrimRange(root_prim or stage.GetPseudoRoot()):
        if prim.HasAPI(UsdSkel.BindingAPI):
            binding = UsdSkel.BindingAPI(prim)
            own = binding.GetJointsAttr()
            if own and own.HasAuthoredValue():
                own.Set([f"{name}/{j}" for j in own.Get()])
            elif prim.IsA(UsdGeom.Mesh):
                binding.CreateJointsAttr().Set([f"{name}/{j}" for j in joints])
    return True


# ----------------------------------------------------------------------------------------------- anatomy
def set_anatomy_purpose(stage, purpose: str) -> int:
    from pxr import UsdGeom

    if not purpose or purpose == "default":
        return 0
    n = 0
    for prim in stage.Traverse():
        if prim.GetName().startswith("bone_") and prim.IsA(UsdGeom.Imageable):
            UsdGeom.Imageable(prim).CreatePurposeAttr().Set(purpose)
            n += 1
    return n


# ----------------------------------------------------------------------------------------------- clothing holes
def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name or "")


def _world_points(prim) -> np.ndarray:
    from pxr import Usd, UsdGeom

    pts = np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float64)
    m = np.asarray(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()), dtype=np.float64)
    return pts @ m[:3, :3] + m[3, :3]


def _triangles(counts, indices) -> np.ndarray:
    tris, k = [], 0
    for n in counts:
        for j in range(1, n - 1):
            tris.append((indices[k], indices[k + j], indices[k + j + 1]))
        k += n
    return np.asarray(tris, dtype=np.int64)


def _vertex_normals(points, tris) -> np.ndarray:
    a, b, c = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    vn = np.zeros_like(points)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    length = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.where(length > 1e-12, length, 1.0)


def covered_vertices(body_pts, body_normals, garment_tris_xyz, max_dist_m=0.07, inside_m=0.006, cell_m=0.05):
    """Body vertices whose outward normal ray hits a garment triangle within [-inside_m, max_dist_m]."""
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
    steps = max(2, int(np.ceil(reach / (cell_m * 0.5))) + 1)
    for v, (p, n) in enumerate(zip(body_pts, body_normals)):
        cells = {tuple(np.floor((p + n * s) / cell_m).astype(int)) for s in np.linspace(-inside_m, max_dist_m, steps)}
        cand = sorted({t for c in cells for t in grid.get(c, ())})
        if not cand:
            continue
        tri = garment_tris_xyz[cand]
        origin = p - n * inside_m
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
        covered[v] = bool((ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (dist >= 0) & (dist <= reach)).any())
    return covered


def clothing_hole_faces(stage, garment_names, max_dist_m=0.07, min_fraction=0.75) -> dict:
    """Author holeIndices on the body mesh for faces covered by the named garments: at least `min_fraction` of the
    face's vertices covered (fewer than all: skin at sleeve ends / armpits pushes out of crumpled sleeves in raised-arm
    poses) and its centre covered too."""
    from pxr import UsdGeom, Vt

    wanted = [_sanitize(n).lower() for n in garment_names if n]
    body, garments = None, []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        if prim.GetName() == BODY_MESH_NAME:
            body = prim
        elif any(w and w in prim.GetParent().GetName().lower() for w in wanted):
            garments.append(prim)
    if body is None or not garments:
        return {"garments": [g.GetParent().GetName() for g in garments], "hole_faces": 0, "faces": 0}
    mesh = UsdGeom.Mesh(body)
    counts = list(mesh.GetFaceVertexCountsAttr().Get())
    indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
    points = _world_points(body)
    normals = _vertex_normals(points, _triangles(counts, indices))
    gtris = []
    for g in garments:
        gm = UsdGeom.Mesh(g)
        tris = _triangles(list(gm.GetFaceVertexCountsAttr().Get()), list(gm.GetFaceVertexIndicesAttr().Get()))
        gtris.append(_world_points(g)[tris])
    gtri = np.concatenate(gtris)
    covered = covered_vertices(points, normals, gtri, max_dist_m)
    # face centres: a face under an opening (collar placket, sleeve end) has covered vertices on both sides of the
    # opening, but its centre looks out through it; such faces must stay, or the opening shows the empty inside
    tris = _triangles(counts, indices)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    centres = np.array([points[indices[k:k + n]].mean(axis=0) for k, n in zip(starts, counts)])
    fnormals = np.array([normals[indices[k:k + n]].mean(axis=0) for k, n in zip(starts, counts)])
    fnormals /= np.maximum(np.linalg.norm(fnormals, axis=1, keepdims=True), 1e-12)
    candidates = [f for f, (k, n) in enumerate(zip(starts, counts)) if covered[indices[k:k + n]].mean() >= min_fraction]
    centre_hit = covered_vertices(centres[candidates], fnormals[candidates], gtri, max_dist_m)
    holes = [f for f, hit in zip(candidates, centre_hit) if hit]
    del tris
    mesh.GetHoleIndicesAttr().Set(Vt.IntArray(holes))
    return {"garments": [g.GetParent().GetName() for g in garments], "hole_faces": len(holes), "faces": len(counts)}


# ----------------------------------------------------------------------------------------------- entry point
def postprocess(usd_path, garment_names, cfg: dict) -> dict:
    """Apply the configured fixes to the exported USD in place. Returns what was done (for the metadata)."""
    from pxr import Usd

    cfg = cfg or {}
    stage = Usd.Stage.Open(str(usd_path))
    info = {}
    if cfg.get("clothing_holes", True):
        info["clothing_holes"] = clothing_hole_faces(stage, garment_names, float(cfg.get("clothing_reach_cm", 7)) / 100.0,
                                                     float(cfg.get("clothing_min_covered_fraction", 0.75)))
    if cfg.get("anatomy_purpose"):
        info["anatomy_purpose"] = {"purpose": cfg["anatomy_purpose"], "prims": set_anatomy_purpose(stage, cfg["anatomy_purpose"])}
    if cfg.get("root_joint"):
        info["root_joint"] = {"name": cfg["root_joint"], "added": add_root_joint(stage, cfg["root_joint"])}
    stage.GetRootLayer().Save()
    return info
