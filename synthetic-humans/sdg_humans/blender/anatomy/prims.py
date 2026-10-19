"""Mesh accumulator and primitives (tubes, ellipsoids, surface patches) for bone meshes.

Every vertex carries skin weights {rig_bone: weight}; to_object() turns them into vertex
groups so the bone mesh follows the armature.
"""

import math

import bpy
from mathutils import Vector


class MeshAcc:
    def __init__(self):
        self.verts, self.weights, self.faces = [], [], []

    def vert(self, co, weights) -> int:
        self.verts.append(tuple(co))
        self.weights.append(weights if isinstance(weights, dict) else {weights: 1.0})
        return len(self.verts) - 1

    def face(self, *indices) -> None:
        self.faces.append(tuple(indices))

    def to_object(self, name: str, material, armature):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.validate(clean_customdata=False)
        mesh.update()
        for poly in mesh.polygons:
            poly.use_smooth = True
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(material)
        groups = {}
        for index, weights in enumerate(self.weights):
            for bone, w in weights.items():
                if bone not in groups:
                    groups[bone] = obj.vertex_groups.new(name=bone)
                groups[bone].add([index], w, "REPLACE")
        obj.parent = armature
        modifier = obj.modifiers.new("Armature", "ARMATURE")
        modifier.object = armature
        return obj


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
