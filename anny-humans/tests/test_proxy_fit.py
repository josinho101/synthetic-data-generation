import numpy as np

from anny_humans.proxy_fit import Mhclo, fit_points, merge_influences, parse_mhclo, transfer_weights


def test_fit_is_weighted_sum_plus_scaled_offset():
    coords = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [2, 2, 2]], dtype=float)
    m = Mhclo(path=None, refs=np.array([[1, 2, 3]]), weights=np.array([[0.5, 0.25, 0.25]]),
              offsets=np.array([[1.0, 2.0, 3.0]]), x_scale=(0, 1, 2.0), y_scale=(0, 3, 4.0), z_scale=(0, 2, 0.5))
    # x size |1-0|/2 = 0.5, y size (z axis) |1-0|/4 = 0.25, z size (y axis) |1-0|/0.5 = 2 -> offset * (0.5, 2, 0.25)
    expected = np.array([0.5, 0.25, 0.25]) + np.array([0.5, 4.0, 0.75])
    assert np.allclose(fit_points(m, coords)[0], expected)


def test_weight_transfer_merges_and_normalises():
    skin_index = np.array([[0, 1], [1, 2], [2, 0]])
    skin_weight = np.array([[1.0, 0.0], [0.5, 0.5], [1.0, 0.0]])
    m = Mhclo(path=None, refs=np.array([[0, 1, 2]]), weights=np.array([[0.5, 0.5, -0.2]]),
              offsets=np.zeros((1, 3)))
    idx, wt = transfer_weights(m, skin_index, skin_weight, 4)
    weights = {int(j): w for j, w in zip(idx[0], wt[0]) if w > 0}     # the negative weight (vertex 2) is ignored
    assert abs(wt.sum() - 1.0) < 1e-9
    assert weights[0] == 0.5 and weights[1] == 0.25 and weights[2] == 0.25


def test_merge_keeps_strongest():
    idx, wt = merge_influences(np.array([[3, 1, 3, 2]]), np.array([[0.2, 0.1, 0.3, 0.4]]), 2)
    assert list(idx[0]) == [3, 2] and np.allclose(wt[0], [0.5 / 0.9, 0.4 / 0.9])


def test_parse_material_inside_verts_block(tmp_path):
    path = tmp_path / "lashes.mhclo"
    path.write_text("name lashes\nobj_file lashes.obj\nverts 0\nmaterial lashes.mhmat\n14742\n"
                    "1 2 3 0.2 0.3 0.5 0.1 0.2 0.3\n\ndelete_verts\n5 - 8 10\n")
    m = parse_mhclo(path)
    assert len(m.refs) == 2 and m.refs[0].tolist() == [14742] * 3
    assert np.allclose(m.offsets[1], [0.1, -0.3, 0.2])          # (d0, -d2, d1): MakeHuman Y-up -> Z-up
    assert m.delete_verts == [5, 6, 7, 8, 10]
