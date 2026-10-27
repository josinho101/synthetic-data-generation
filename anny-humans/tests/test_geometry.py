import numpy as np
import pytest

trimesh = pytest.importorskip("trimesh")

from anny_humans.geometry import MeshBVH, RadialDepth  # noqa: E402


def _sphere(radius=0.1):
    mesh = trimesh.creation.icosphere(subdivisions=4, radius=radius)
    return np.asarray(mesh.vertices), np.asarray(mesh.faces)


def test_nearest_matches_trimesh():
    points, tris = _sphere()
    bvh = MeshBVH(points, tris)
    q = np.random.default_rng(1).normal(0, 0.08, (500, 3))
    _loc, _n, _f, dist = bvh.find_nearest_many(q)
    _l, ref, _t = trimesh.proximity.closest_point(bvh.mesh, q)
    assert np.abs(dist - ref).max() < 1e-4


def test_ray_cast_and_radial_depth_on_a_sphere():
    points, tris = _sphere()
    bvh = MeshBVH(points, tris)
    hit = bvh.ray_cast([0, 0, 0], [0, 1, 0], 1.0)
    assert hit[0] is not None and abs(hit[3] - 0.1) < 2e-3
    depth = RadialDepth(points, tris, [0, 0, 0])
    d = depth.first_hit(np.random.default_rng(2).normal(0, 1, (200, 3)), 0.4)
    assert np.all(np.abs(d - 0.1) < 3e-3)
