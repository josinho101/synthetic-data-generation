import math

import numpy as np

from anny_humans import anatomy_rules as ar
from anny_humans import pose_rules as pr

LEVELS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10",
          "T11", "T12", "L1", "L2", "L3", "L4", "L5", "S1", "S2", "S3", "S4", "S5"]


def _straight_spine():
    return [np.array([0.0, 0.05, 1.55 - 0.024 * i]) for i in range(len(LEVELS))]


def test_reshape_spine_hits_targets():
    shape = {"kyphosis_T4_T12_deg": 40.0, "lordosis_L1_S1_deg": 50.0, "scoliosis_cobb_deg": 20.0,
             "scoliosis_apex": "T8", "scoliosis_convex": "right"}
    new, rot = ar.reshape_spine(_straight_spine(), LEVELS, shape)
    got = ar.spine_curvature(new, LEVELS)
    assert abs(got["kyphosis_T4_T12_deg"] - 40) < 1.5 and abs(got["lordosis_L1_S1_deg"] - 50) < 1.5
    assert abs(got["scoliosis_cobb_deg"] - 20) < 1.5
    apex = LEVELS.index("T8")
    assert new[apex][0] < 0                              # convex to the subject's right (-X)
    assert np.allclose(new[-1], _straight_spine()[-1])   # sacrum fixed
    assert abs(rot).max() > 0


def test_harrington_hip_centre():
    P = {"asis_L": (0.12, -0.10, 1.0), "asis_R": (-0.12, -0.10, 1.0), "psis_L": (0.045, 0.08, 1.0),
         "psis_R": (-0.045, 0.08, 1.0)}
    c = ar.joint_centres({k: np.array(v) for k, v in P.items()})
    hl, hr = c["hip_centre_L"], c["hip_centre_R"]
    assert hl[0] > 0 > hr[0] and abs(hl[0] + hr[0]) < 1e-9          # symmetric, left on +X
    assert hl[2] < 1.0 and hl[1] > -0.10                            # inferior and posterior to the ASIS


def test_parent_lookup_patterns():
    m = {"rib*_L": "spine02", "hyoid": "neck02"}
    assert ar.parent_lookup("rib07_L", m) == "spine02" and ar.parent_lookup("hyoid", m) == "neck02"
    assert ar.parent_lookup("rib07_R", m, "root") == "root"


def test_rotation_helpers():
    R = pr.arc([1, 0, 0], [0, 1, 0])
    assert np.allclose(R @ [1, 0, 0], [0, 1, 0])
    half = pr.slerp(np.eye(3), pr.rot([0, 0, 1], 90), 0.5)
    assert np.allclose(half, pr.rot([0, 0, 1], 45), atol=1e-9)


def test_validate_flags_out_of_range():
    bad = pr.validate({"elbow_flexion_L": -25.0, "knee_flexion_R": 20.0, "trunk_flexion": 10.0})
    assert [b["angle"] for b in bad] == ["elbow_flexion_L"]
    assert math.isclose(bad[0]["value"], -25.0)
