"""Mesh queries without Blender: a BVH-like wrapper (trimesh) and a small mathutils.Vector stand-in.

MeshBVH mirrors mathutils.bvhtree.BVHTree.ray_cast / find_nearest (same return tuples), so code ported from the
MPFB Blender pipeline keeps its structure.
"""

import numpy as np


class Vector:
    """Minimal 3-D vector with the mathutils.Vector API used by the anatomy builders."""

    __slots__ = ("_v",)

    def __init__(self, values=(0.0, 0.0, 0.0)):
        self._v = np.array(values, dtype=np.float64).reshape(3)

    x = property(lambda self: float(self._v[0]), lambda self, v: self._v.__setitem__(0, v))
    y = property(lambda self: float(self._v[1]), lambda self, v: self._v.__setitem__(1, v))
    z = property(lambda self: float(self._v[2]), lambda self, v: self._v.__setitem__(2, v))

    def __iter__(self):
        return iter(float(c) for c in self._v)

    def __len__(self):
        return 3

    def __getitem__(self, i):
        return float(self._v[i])

    def __array__(self, dtype=None, copy=None):
        return self._v.astype(dtype) if dtype else self._v.copy()

    def __add__(self, o):
        return Vector(self._v + np.asarray(o, dtype=np.float64))

    __radd__ = __add__

    def __sub__(self, o):
        return Vector(self._v - np.asarray(o, dtype=np.float64))

    def __rsub__(self, o):
        return Vector(np.asarray(o, dtype=np.float64) - self._v)

    def __mul__(self, s):
        return Vector(self._v * float(s))

    __rmul__ = __mul__

    def __truediv__(self, s):
        return Vector(self._v / float(s))

    def __neg__(self):
        return Vector(-self._v)

    def __repr__(self):
        return f"Vector({self.x:.4f}, {self.y:.4f}, {self.z:.4f})"

    def copy(self):
        return Vector(self._v)

    def dot(self, o) -> float:
        return float(self._v @ np.asarray(o, dtype=np.float64))

    def cross(self, o):
        return Vector(np.cross(self._v, np.asarray(o, dtype=np.float64)))

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self._v))

    @property
    def length_squared(self) -> float:
        return float(self._v @ self._v)

    def normalized(self):
        n = self.length
        return Vector(self._v / n) if n > 0 else Vector(self._v)

    def normalize(self) -> None:
        n = self.length
        if n > 0:
            self._v /= n

    def lerp(self, o, f: float):
        return Vector(self._v + (np.asarray(o, dtype=np.float64) - self._v) * float(f))


def triangulate(faces) -> np.ndarray:
    """Polygons (list of index lists, or an [F, 4] array padded with -1) -> [T, 3] triangles (fan)."""
    tris = []
    for face in faces:
        face = [int(i) for i in face if i >= 0]
        tris.extend((face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1))
    return np.asarray(tris, dtype=np.int64).reshape(-1, 3)


def vertex_normals(points, tris) -> np.ndarray:
    a, b, c = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    vn = np.zeros_like(points, dtype=np.float64)
    for k in range(3):
        np.add.at(vn, tris[:, k], fn)
    length = np.linalg.norm(vn, axis=1, keepdims=True)
    return vn / np.where(length > 1e-12, length, 1.0)


def _closest_on_triangles(p, a, b, c):
    """Closest points on triangles (a, b, c) to p, broadcast over leading axes (Ericson, Real-Time Collision
    Detection 5.1.5)."""
    ab, ac, ap = b - a, c - a, p - a
    d1, d2 = np.einsum("...k,...k->...", ab, ap), np.einsum("...k,...k->...", ac, ap)
    bp = p - b
    d3, d4 = np.einsum("...k,...k->...", ab, bp), np.einsum("...k,...k->...", ac, bp)
    cp = p - c
    d5, d6 = np.einsum("...k,...k->...", ab, cp), np.einsum("...k,...k->...", ac, cp)
    va, vb, vc = d3 * d6 - d5 * d4, d5 * d2 - d1 * d6, d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = 1.0 / (va + vb + vc)
        v, w = vb * denom, vc * denom
        out = a + ab * v[..., None] + ac * w[..., None]                                  # face region
        t_bc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        out = np.where(((va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0))[..., None], b + (c - b) * t_bc[..., None], out)
        t_ac = d2 / (d2 - d6)
        out = np.where(((vb <= 0) & (d2 >= 0) & (d6 <= 0))[..., None], a + ac * t_ac[..., None], out)
        t_ab = d1 / (d1 - d3)
        out = np.where(((vc <= 0) & (d1 >= 0) & (d3 <= 0))[..., None], a + ab * t_ab[..., None], out)
    out = np.where(((d6 >= 0) & (d5 <= d6))[..., None], c, out)
    out = np.where(((d3 >= 0) & (d4 <= d3))[..., None], b, out)
    out = np.where(((d1 <= 0) & (d2 <= 0))[..., None], a, out)
    return out


class MeshBVH:
    """Ray casts and nearest-point queries on a triangle mesh (world space, metres)."""

    def __init__(self, points, tris):
        import trimesh
        tris = np.asarray(tris, dtype=np.int64)
        self.mesh = trimesh.Trimesh(np.asarray(points, dtype=np.float64), tris, process=False)
        self.normals = self.mesh.face_normals
        self._rays = trimesh.ray.ray_triangle.RayMeshIntersector(self.mesh)
        self._kd = None
        self._vertex_tris = None

    # ---- single queries (mathutils API) ----
    def ray_cast(self, origin, direction, distance=1e9):
        """-> (location Vector | None, normal, face index, distance) of the first hit within distance."""
        hit = self.ray_cast_many([tuple(origin)], [tuple(direction)], distance)
        if hit[0][0] is None:
            return None, None, None, None
        return hit[0]

    def find_nearest(self, point, distance=1e9):
        loc, normal, index, dist = self.find_nearest_many([tuple(point)])
        if dist[0] > distance:
            return None, None, None, None
        return Vector(loc[0]), Vector(normal[0]), int(index[0]), float(dist[0])

    # ---- batched queries ----
    def ray_cast_many(self, origins, directions, distance=1e9) -> list:
        origins = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
        directions = np.asarray(directions, dtype=np.float64).reshape(-1, 3)
        directions = directions / np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-12)
        out = [(None, None, None, None)] * len(origins)
        if not len(origins):
            return out
        locs, rays, faces = self._rays.intersects_location(origins, directions, multiple_hits=False)
        best = {}
        for loc, ray, face in zip(locs, rays, faces):
            d = float(np.dot(loc - origins[ray], directions[ray]))
            if 1e-7 < d <= distance and (ray not in best or d < best[ray][3]):
                best[ray] = (Vector(loc), Vector(self.normals[face]), int(face), d)
        for ray, value in best.items():
            out[ray] = value
        return out

    def hits_any(self, origins, directions, distance) -> np.ndarray:
        """[N] bool: does the ray hit the mesh within distance."""
        return np.array([h[0] is not None for h in self.ray_cast_many(origins, directions, distance)], dtype=bool)

    def find_nearest_many(self, points, k: int = 12):
        """Closest surface point per query: the triangles around the k nearest vertices are tested exactly
        (vectorised point-triangle distance). Exact for meshes with even, small triangles such as the body."""
        from scipy.spatial import cKDTree
        points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        if self._kd is None:
            tris = np.asarray(self.mesh.faces)
            self._used = np.unique(tris)                       # vertices that belong to a triangle
            self._kd = cKDTree(self.mesh.vertices[self._used])
            order = np.argsort(tris.reshape(-1), kind="stable")
            owners = (order // 3)
            counts = np.bincount(tris.reshape(-1), minlength=len(self.mesh.vertices))
            width = int(counts.max())
            table = np.full((len(self.mesh.vertices), width), -1, dtype=np.int64)
            starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
            slot = np.arange(len(order)) - np.repeat(starts, counts)
            table[np.repeat(np.arange(len(counts)), counts), slot] = owners
            self._vertex_tris = table
        _d, near = self._kd.query(points, k=min(k, len(self._used)))
        cand = self._vertex_tris[self._used[np.asarray(near)].reshape(len(points), -1)].reshape(len(points), -1)   # [N, C]
        valid = cand >= 0
        tri = self.mesh.triangles[np.where(valid, cand, 0)]                                           # [N, C, 3, 3]
        closest = _closest_on_triangles(points[:, None, :], tri[:, :, 0], tri[:, :, 1], tri[:, :, 2])
        dist = np.linalg.norm(closest - points[:, None, :], axis=2)
        dist = np.where(valid, dist, np.inf)
        best = np.argmin(dist, axis=1)
        rows = np.arange(len(points))
        face = cand[rows, best]
        return closest[rows, best], self.normals[face], face, dist[rows, best]

    def signed_distance_out(self, points):
        """-> (nearest location, face normal, distance along the normal (+ outside), distance) per point."""
        loc, normal, _face, dist = self.find_nearest_many(points)
        return loc, normal, np.einsum("ij,ij->i", np.asarray(points) - loc, normal), dist



class RadialDepth:
    """First surface hit along rays from one centre point, as a spherical min-radius map.

    The surface is sampled densely (random barycentric points per triangle) and binned by direction; a ray's first
    hit is the smallest radius in its bin (and the neighbouring bins, to stay conservative). Bins without samples are
    open directions (mouth, nostrils). Much faster than ray casting when thousands of rays share the centre."""

    def __init__(self, points, tris, centre, bins_deg: float = 1.0, samples_per_m2: float = 4e6, seed: int = 0):
        self.centre = np.asarray(centre, dtype=np.float64)
        self.n_theta, self.n_phi = int(round(180 / bins_deg)), int(round(360 / bins_deg))
        tri = np.asarray(points, dtype=np.float64)[np.asarray(tris)]
        area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
        counts = np.maximum(3, np.ceil(area * samples_per_m2)).astype(np.int64)
        owner = np.repeat(np.arange(len(tri)), counts)
        rng = np.random.default_rng(seed)
        r1, r2 = np.sqrt(rng.random(len(owner))), rng.random(len(owner))
        bary = np.stack([1 - r1, r1 * (1 - r2), r1 * r2], axis=1)
        samples = np.einsum("nk,nkd->nd", bary, tri[owner])
        samples = np.concatenate([samples, tri.reshape(-1, 3)])
        r, ti, pi = self._bins(samples)
        depth = np.full((self.n_theta, self.n_phi), np.inf)
        np.minimum.at(depth, (ti, pi), r)
        from scipy.ndimage import minimum_filter
        self.depth = minimum_filter(depth, size=3, mode="wrap")

    def _bins(self, pts):
        d = np.asarray(pts, dtype=np.float64) - self.centre
        r = np.linalg.norm(d, axis=1)
        theta = np.arccos(np.clip(d[:, 2] / np.maximum(r, 1e-12), -1, 1))
        phi = np.arctan2(d[:, 1], d[:, 0]) + np.pi
        ti = np.clip((theta / np.pi * self.n_theta).astype(np.int64), 0, self.n_theta - 1)
        pi = np.clip((phi / (2 * np.pi) * self.n_phi).astype(np.int64), 0, self.n_phi - 1) % self.n_phi
        return r, ti, pi

    def first_hit(self, pts, max_distance: float) -> np.ndarray:
        """[N] distance from the centre to the first surface hit towards each point (inf = open direction)."""
        _r, ti, pi = self._bins(pts)
        hit = self.depth[ti, pi]
        return np.where(hit <= max_distance, hit, np.inf)
