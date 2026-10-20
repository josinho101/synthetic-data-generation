import math

import numpy as np
import pytest

from sdg_room.photometry import solve_luminance, unit_illuminance


def test_small_panel_matches_point_source():
    """E = L * A * cos^2 / d^2 (both cosines) for a tiny emitter."""
    h, area = 2.5, 0.01 ** 2
    for r in (0.0, 1.0, 2.0):
        e = unit_illuminance(np.array([[r, 0.0]]), [{"center": [0, 0], "size_m": [0.01, 0.01]}], h, subdiv=2)[0]
        d2 = r * r + h * h
        assert e == pytest.approx(area * (h * h / d2) / d2, rel=1e-3)


def test_infinite_plane_gives_pi_times_luminance():
    e = unit_illuminance(np.array([[0.0, 0.0]]), [{"center": [0, 0], "size_m": [400, 400]}], 2.5, subdiv=800)[0]
    assert e == pytest.approx(math.pi, rel=0.02)


def test_solver_hits_target_mean():
    pts = np.array([[x, y] for x in np.arange(0.1, 5, 0.2) for y in np.arange(0.1, 2.5, 0.2)])
    panels = [{"center": [1.5, 1.25], "size_m": [1.2, 0.6]}, {"center": [3.5, 1.25], "size_m": [1.2, 0.6]}]
    res = solve_luminance(500, pts, panels, 2.7, indirect_gain=1.25, calibration=1.0)
    assert res["estimated_lux_mean"] == pytest.approx(500)
    assert res["direct_lux_mean"] == pytest.approx(400)
    assert 1000 < res["luminance_nits"] < 20000
