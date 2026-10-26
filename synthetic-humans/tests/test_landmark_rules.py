import numpy as np

from sdg_humans import landmark_rules as rules


def _check_axes(axes):
    assert np.allclose(axes.T @ axes, np.eye(3), atol=1e-9)
    assert np.isclose(np.linalg.det(axes), 1.0)


def test_frames_axis_directions():
    lm = {"asis_L": (0.12, -0.10, 1.0), "asis_R": (-0.12, -0.10, 1.0), "psis_L": (0.045, 0.08, 1.0),
          "psis_R": (-0.045, 0.08, 1.0), "jugular_notch": (0, -0.08, 1.45), "xiphoid": (0, -0.12, 1.28),
          "C7_surf": (0, 0.06, 1.50), "T8_surf": (0, 0.10, 1.30),
          "acromion_L": (0.19, 0.0, 1.47), "scapula_spine_root_L": (0.08, 0.09, 1.42),
          "scapula_inferior_angle_L": (0.09, 0.10, 1.30),
          "acromion_R": (-0.19, 0.0, 1.47), "scapula_spine_root_R": (-0.08, 0.09, 1.42),
          "scapula_inferior_angle_R": (-0.09, 0.10, 1.30),
          "tragus_L": (0.07, -0.05, 1.62), "tragus_R": (-0.07, -0.05, 1.62),
          "infraorbital_L": (0.03, -0.12, 1.62), "infraorbital_R": (-0.03, -0.12, 1.62)}
    frames = rules.anatomical_frames(lm)
    assert set(frames) == {"pelvis", "thorax", "scapula_L", "scapula_R", "skull"}
    for name, (origin, axes) in frames.items():
        _check_axes(axes)
        assert axes[:, 0] @ rules.ANTERIOR > 0.5, name       # X anterior
        assert axes[:, 1] @ rules.SUPERIOR > 0.5, name       # Y superior
        assert axes[:, 2] @ rules.RIGHT > 0.5, name          # Z subject right
    assert np.allclose(frames["pelvis"][0], (0, -0.10, 1.0))


def test_spine_axes_follow_curve():
    centres = [(0, 0.0, 1.5), (0, 0.01, 1.4), (0, 0.03, 1.3)]
    for axes in rules.spine_axes(centres):
        _check_axes(axes)
        assert axes[:, 1][2] > 0.9 and axes[:, 2] @ rules.RIGHT > 0.99
