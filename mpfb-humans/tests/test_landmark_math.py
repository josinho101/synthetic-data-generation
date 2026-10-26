from sdg_humans import landmark_math as lm


def test_distribute_levels_between_boundaries():
    levels = ["A", "B", "C"]
    pos = lm.distribute_levels(levels, {"A": 1, "B": 1, "C": 2}, {}, 0.0, 4.0)
    assert pos == {"A": 0.5, "B": 1.5, "C": 3.0}


def test_pinned_level_is_respected_and_order_monotonic():
    levels = ["C1", "C2", "C3", "C4"]
    ratios = {k: 1.0 for k in levels}
    pos = lm.distribute_levels(levels, ratios, {"C3": 10.0}, 0.0, 14.0)
    assert pos["C3"] == 10.0
    assert pos["C1"] < pos["C2"] < pos["C3"] < pos["C4"]


def test_polyline_projection_round_trip():
    line = [(0, 0, 2), (0, 0, 1), (0, 0, 0)]
    s = lm.project_to_arc(line, (0.1, 0, 0.5))
    assert abs(s - 1.5) < 1e-9
    assert lm.point_at_arc(line, s) == (0, 0, 0.5)


def test_posterior_profile_rejects_front_points():
    chain = [(0, 0.05, 1.0), (0, 0.05, 0.0)]
    points = [(0, 0.06, 0.55), (0, -0.12, 0.45)]  # back point, belly point
    profile = lm.posterior_profile(points, chain)
    assert (0, 0.06, 0.55) in profile and (0, -0.12, 0.45) not in profile


def test_expand_parent_map():
    levels = ["T1", "T2", "T3", "T4", "T5"]
    out = lm.expand_parent_map({"T1-T4": "spine05", "tragus_{side}": "head", "asis_{side}": "pelvis.{side}"}, levels)
    assert out["T3"] == "spine05" and "T5" not in out
    assert out["tragus_L"] == "head" and out["asis_R"] == "pelvis.R"
