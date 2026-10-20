import json
from collections import Counter

from sdg_room.config import apply_overrides
from sdg_room.sampling.distributions import room_rng, truncated_normal
from sdg_room.sampling.manifest import build_room_spec, build_specs


def test_same_seed_gives_identical_specs(cfg):
    small = apply_overrides(cfg, {"variations.count": 4})
    a, b = build_specs(small), build_specs(small)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


def test_different_seed_changes_rooms(cfg):
    a = build_room_spec(cfg, 0)
    b = build_room_spec(apply_overrides(cfg, {"variations.seed": cfg["variations"]["seed"] + 1}), 0)
    assert a["seed"] != b["seed"]


def test_rooms_differ_from_each_other(cfg):
    specs = build_specs(apply_overrides(cfg, {"variations.count": 6}))
    keys = {(s["wall_finish"], s["floor_material"], s["cct_k"], s["lux_target"]) for s in specs}
    assert len(keys) == 6


def test_ranges_are_respected(cfg):
    lux, light = cfg["lighting"]["lux"], cfg["lighting"]
    for i in range(25):
        s = build_room_spec(cfg, i)
        assert lux["min"] <= s["lux_target"] <= lux["max"]
        lo, hi = light["cct_k"][s["cct_class"]]
        assert lo <= s["cct_k"] <= hi
        sid = s["layout"]["equipment"]["sid_m"]
        assert cfg["equipment"]["tube_stand"]["sid_m"][0] <= sid <= cfg["equipment"]["tube_stand"]["sid_m"][1]
        h = s["layout"]["equipment"]["detector"]["center"][2]
        assert cfg["equipment"]["wall_stand"]["carriage_travel_m"][0] <= h <= cfg["equipment"]["wall_stand"]["carriage_travel_m"][1]


def test_categorical_frequencies_follow_weights(cfg):
    """Spec sampling only (no layout): 2000 draws match the configured weights within 4 points."""
    from sdg_room.sampling.sampler import sample_spec
    counts = Counter()
    n = 2000
    for i in range(n):
        counts[sample_spec(cfg, i, "R", room_rng(1, i), 0, 0)["cct_class"]] += 1
    weights = cfg["variations"]["cct_class"]
    total = sum(weights.values())
    for key, w in weights.items():
        assert abs(100.0 * counts[key] / n - 100.0 * w / total) < 4.0


def test_lux_distribution_mean_near_500(cfg):
    rng = room_rng(3, 0)
    lux = cfg["lighting"]["lux"]
    values = [truncated_normal(rng, lux["mean"], lux["sd"], lux["min"], lux["max"]) for _ in range(4000)]
    assert abs(sum(values) / len(values) - 500) < 15
    assert min(values) >= 100 and max(values) <= 1000


def test_floor_and_wall_colours_always_differ(cfg):
    from sdg_room.sampling.distributions import delta_e, room_rng
    from sdg_room.sampling.sampler import sample_spec
    minimum = cfg["materials"]["min_floor_wall_delta_e"]
    corrected = 0
    for i in range(300):
        s = sample_spec(cfg, i, "R", room_rng(5, i), 0, 0)
        assert delta_e(s["floor"]["color"], s["walls"]["color"]) >= minimum - 1e-6
        corrected += "color_sampled" in s["floor"]
    assert corrected > 0          # the default palettes do produce close pairs that get corrected


def test_lab_round_trip():
    from sdg_room.sampling.distributions import hex_to_lab, lab_to_hex
    for c in ("#f2f1ec", "#8e8a84", "#1f3b73", "#e6dcc8"):
        assert lab_to_hex(hex_to_lab(c)) == c
