"""Z-Anatomy fit: FK keeps joints connected under scaling, and fitting into the reference skin itself recovers the
reference skeleton. Needs torch + scipy and the reference package (scripts/build_zanatomy_reference.py)."""

import numpy as np
import pytest

from sdg_humans.skeleton.zanatomy.reference import check, load, resolve_dir

pytest.importorskip("torch")
pytest.importorskip("scipy")
REF_DIR = resolve_dir({})
pytestmark = pytest.mark.skipif(not check(REF_DIR)[0], reason="Z-Anatomy reference package not built")


@pytest.fixture(scope="module")
def ref():
    return load(str(REF_DIR))


def _ref_body(ref):
    V = ref.data["ref_skin"].astype(np.float64)
    F = ref.data["ref_skin_faces"]
    tris = np.concatenate([F[:, [0, 1, 2]], F[F[:, 3] >= 0][:, [0, 2, 3]]])
    return V, tris


def test_fit_into_reference_recovers_reference(ref):
    from sdg_humans.skeleton.zanatomy.fit import fit
    V, tris = _ref_body(ref)
    out = fit(ref, V, tris, bmi=23.5, cfg={"iters": 200})
    m = out["metrics"]
    # the reference skin meets the tissue depths only approximately (S4 fit), so ~9 mm is the floor here
    assert m["landmark_residual_mm"]["median"] < 12.0
    assert 0.9 < m["scale_rel_to_stature"]["length"][1] < 1.1
    assert m["lr_scale_diff_max"] < 0.05
    # joints connected: every child's head lies on its parent's scaled frame (FK attaches children there)
    W, S, parent = out["W"], out["S"], ref.parent
    M, Minv = ref.frames, np.linalg.inv(ref.frames)
    for i in range(1, len(parent)):
        p = parent[i]
        if p < 0:
            continue
        local = (Minv[p] @ M[i])[:3, 3] * S[p]
        assert np.allclose(W[p][:3, :3] @ local + W[p][:3, 3], W[i][:3, 3], atol=1e-6)
