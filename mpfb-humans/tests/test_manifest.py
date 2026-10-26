from collections import Counter

from sdg_humans.sampling.anthropometrics import age_to_mpfb
from sdg_humans.sampling.identity import identity_distance
from sdg_humans.sampling.manifest import build_specs


def test_manifest_counts_and_quotas(cfg, catalogue):
    cfg["population"]["count"] = 40
    specs = build_specs(cfg, catalogue)
    assert len(specs) == 40
    assert Counter(s["sex"] for s in specs) == {"male": 20, "female": 20}
    assert len({s["id"] for s in specs}) == 40


def test_clothing_disabled_gives_unclothed_humans(cfg, catalogue):
    cfg["population"]["count"] = 12
    cfg["clothing"]["enabled"] = False
    assert {s["clothing_variant"] for s in build_specs(cfg, catalogue)} == {"none"}


def test_manifest_is_deterministic(cfg, catalogue):
    cfg["population"]["count"] = 10
    assert build_specs(cfg, catalogue) == build_specs(cfg, catalogue)


def test_seed_changes_population(cfg, catalogue):
    cfg["population"]["count"] = 10
    first = build_specs(cfg, catalogue)
    cfg["population"]["seed"] += 1
    assert first != build_specs(cfg, catalogue)


def test_uniqueness_threshold(cfg, catalogue):
    cfg["population"]["count"] = 30
    specs = build_specs(cfg, catalogue)
    threshold = cfg["population"]["uniqueness"]["min_feature_distance"]
    for i, a in enumerate(specs):
        for b in specs[:i]:
            assert identity_distance(a, b) >= threshold * 0.999 or a["uniqueness_distance"] < threshold


def test_spec_values_in_range(cfg, catalogue):
    cfg["population"]["count"] = 30
    for s in build_specs(cfg, catalogue):
        m = s["macros"]
        assert abs(sum(m["race"].values()) - 1.0) < 1e-3
        rng = cfg["population"]["somatotype"][s["somatotype"]]
        assert rng["weight"][0] <= m["weight"] <= rng["weight"][1]
        lo, hi = map(int, s["age_band"].split("-"))
        assert lo <= s["age_years"] <= hi


def test_age_mapping():
    mapping = [[1, 0.0], [25, 0.5], [90, 1.0]]
    assert age_to_mpfb(25, mapping) == 0.5
    assert age_to_mpfb(100, mapping) == 1.0
    assert 0.5 < age_to_mpfb(50, mapping) < 1.0
