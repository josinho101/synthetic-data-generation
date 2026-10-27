"""Mesh accumulator and primitives (tubes, ellipsoids, surface patches) for bone meshes.

Every vertex carries skin weights {rig_bone: weight}; the USD writer turns them into joint indices / weights so
the bone mesh follows the skeleton. Port of the MPFB Blender version (same primitives, no bpy).
"""

import math

import numpy as np

from ..geometry import Vector, triangulate, vertex_normals


class MeshAcc:
    def __init__(self):
        self.verts, self.weights, self.faces = [], [], []

    def vert(self, co, weights) -> int:
        self.verts.append(tuple(co))
        self.weights.append(weights if isinstance(weights, dict) else {weights: 1.0})
        return len(self.verts) - 1

    def face(self, *indices) -> None:
        self.faces.append(tuple(indices))

    def arrays(self) -> tuple:
        """-> (points [N, 3], triangles [T, 3], weights [N] dicts)."""
        return np.asarray(self.verts, dtype=np.float64).reshape(-1, 3), triangulate(self.faces), list(self.weights)


def _mix(a: dict, b: dict) -> dict:
    out = {}
    for weights in (a, b):
        for bone, w in weights.items():
            out[bone] = out.get(bone, 0.0) + 0.5 * w
    return out


def subdivide(points, tris, weights, max_edge_m: float, passes: int = 3) -> tuple:
    """Split triangles with an edge longer than max_edge_m into four (shared edge midpoints, weights averaged),
    so no bone triangle spans a skin concavity while all its corners are inside."""
    points, weights = [p for p in np.asarray(points)], list(weights)
    tris = [tuple(t) for t in tris]
    for _ in range(passes):
        long = {t for t in tris if any(np.linalg.norm(points[t[a]] - points[t[(a + 1) % 3]]) > max_edge_m
                                       for a in range(3))}
        if not long:
            break
        mids, out = {}, []

        def mid(i, j):
            key = (min(i, j), max(i, j))
            if key not in mids:
                points.append((points[i] + points[j]) / 2.0)
                weights.append(_mix(weights[i], weights[j]))
                mids[key] = len(points) - 1
            return mids[key]

        for t in tris:
            if t in long:
                a, b, c = t
                ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
                out += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
            else:
                out.append(t)
        # neighbours of split triangles that were not split themselves get a T-junction; close it with a fan
        # around the triangle's centre (no degenerate slivers)
        fixed = []
        for t in out:
            ring = []
            for a in range(3):
                e = (t[a], t[(a + 1) % 3])
                ring.append(e[0])
                m = mids.get((min(e), max(e)))
                if m is not None and m not in t:
                    ring.append(m)
            if len(ring) == 3:
                fixed.append(t)
                continue
            points.append(np.mean([points[i] for i in t], axis=0))
            weights.append(_mix(_mix(weights[t[0]], weights[t[1]]), weights[t[2]]))
            centre = len(points) - 1
            fixed += [(ring[k], ring[(k + 1) % len(ring)], centre) for k in range(len(ring))]
        tris = fixed
    return np.asarray(points), np.asarray(tris, dtype=np.int64), weights


def solidify(points, tris, weights, thickness: float) -> tuple:
    """Two offset shells (+/- thickness / 2 along the vertex normals), the inner one flipped."""
    n = vertex_normals(points, tris)
    half = n * thickness / 2.0
    pts = np.concatenate([points + half, points - half])
    inner = tris[:, ::-1] + len(points)
    return pts, np.concatenate([tris, inner]), weights + weights


def _frame(tangent: Vector, hint: Vector):
    t = tangent.normalized()
    side = hint - t * hint.dot(t)
    if side.length < 1e-6:
        side = Vector((0, 0, 1)) - t * t.z
        if side.length < 1e-6:
            side = Vector((1, 0, 0))
    side.normalize()
    return side, t.cross(side)


def tube(acc: MeshAcc, points, radius, weights_fn, segments=8, radius_y=None, hint=Vector((1, 0, 0)), caps=True):
    """Tube along a polyline. radius / radius_y: number or per-point list (elliptical section,
    radius along `hint`, radius_y perpendicular). weights_fn(t in 0..1) -> {bone: w}."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    rx = radius if isinstance(radius, (list, tuple)) else [radius] * n
    ry = radius_y if isinstance(radius_y, (list, tuple)) else ([radius_y] * n if radius_y else rx)
    rings = []
    for k, p in enumerate(pts):
        tangent = (pts[min(k + 1, n - 1)] - pts[max(k - 1, 0)])
        u, w = _frame(tangent, hint)
        weights = weights_fn(k / (n - 1) if n > 1 else 0.0)
        rings.append([acc.vert(p + (u * math.cos(2 * math.pi * m / segments) * rx[k] +
                                   w * math.sin(2 * math.pi * m / segments) * ry[k]), weights)
                      for m in range(segments)])
    for a, b in zip(rings, rings[1:]):
        for m in range(segments):
            acc.face(a[m], a[(m + 1) % segments], b[(m + 1) % segments], b[m])
    if caps:
        for ring, p, flip in ((rings[0], pts[0], True), (rings[-1], pts[-1], False)):
            c = acc.vert(p, acc.weights[ring[0]])
            for m in range(segments):
                pair = (ring[(m + 1) % segments], ring[m]) if flip else (ring[m], ring[(m + 1) % segments])
                acc.face(c, *pair)


def ellipsoid(acc: MeshAcc, centre, radii, weights, axes=None, rings=8, segments=12):
    """Ellipsoid; axes = (x, y, z) unit vectors (default world axes)."""
    ax = axes or (Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)))
    c = Vector(centre)
    top = acc.vert(c + ax[2] * radii[2], weights)
    grid = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        grid.append([acc.vert(c + ax[0] * (radii[0] * math.sin(phi) * math.cos(2 * math.pi * m / segments)) +
                              ax[1] * (radii[1] * math.sin(phi) * math.sin(2 * math.pi * m / segments)) +
                              ax[2] * (radii[2] * math.cos(phi)), weights) for m in range(segments)])
    bottom = acc.vert(c - ax[2] * radii[2], weights)
    for m in range(segments):
        acc.face(top, grid[0][m], grid[0][(m + 1) % segments])
        acc.face(bottom, grid[-1][(m + 1) % segments], grid[-1][m])
    for a, b in zip(grid, grid[1:]):
        for m in range(segments):
            acc.face(a[m], b[m], b[(m + 1) % segments], a[(m + 1) % segments])


def patch(acc: MeshAcc, grid_points, weights) -> None:
    """Quad surface from a 2-D list of points (rows x cols); thickness comes from Solidify."""
    ids = [[acc.vert(p, weights) for p in row] for row in grid_points]
    for r in range(len(ids) - 1):
        for c in range(len(ids[0]) - 1):
            acc.face(ids[r][c], ids[r][c + 1], ids[r + 1][c + 1], ids[r + 1][c])


def bilinear(a, b, c, d, rows=5, cols=5):
    """Grid over the quad a-b (top edge), d-c (bottom edge)."""
    a, b, c, d = (Vector(p) for p in (a, b, c, d))
    return [[(a.lerp(b, j / (cols - 1))).lerp(d.lerp(c, j / (cols - 1)), i / (rows - 1)) for j in range(cols)]
            for i in range(rows)]


def blend(bone_a: str, bone_b: str, split: float = 0.5, width: float = 0.15):
    """weights_fn that hands over from bone_a to bone_b around t = split (twist bones)."""
    def fn(t):
        w = min(1.0, max(0.0, (t - split + width) / (2 * width)))
        return {bone_a: 1.0 - w, bone_b: w} if 0.0 < w < 1.0 else ({bone_b: 1.0} if w >= 1.0 else {bone_a: 1.0})
    return fn
