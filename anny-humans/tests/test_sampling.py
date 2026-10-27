import copy
import itertools

from anny_humans.sampling.anthropometrics import age_to_anny
from anny_humans.sampling.identity import identity_distance
from anny_humans.sampling.manifest import build_specs


def test_ages_stay_inside_the_configured_range(cfg, catalogue):
    cfg["population"]["count"] = 60
    for lo, hi in ((18, 70), (25, 40), (50, 70)):
        c = copy.deepcopy(cfg)
        c["population"]["age_range"] = {"min": lo, "max": hi}
        from anny_humans.config.loader import _apply_age_range
        _apply_age_range(c["population"])
        ages = [s["age_years"] for s in build_specs(c, catalogue)]
        assert min(ages) >= lo and max(ages) <= hi


def test_humans_are_unique(cfg, catalogue):
    cfg["population"]["count"] = 40
    specs = build_specs(cfg, catalogue)
    threshold = cfg["population"]["uniqueness"]["min_feature_distance"]
    assert min(identity_distance(a, b) for a, b in itertools.combinations(specs, 2)) >= threshold


def test_anny_age_mapping_is_calibrated(cfg):
    mapping = cfg["population"]["age_years_to_anny"]
    assert age_to_anny(18, mapping) == 0.77
    assert 0.77 < age_to_anny(40, mapping) < age_to_anny(70, mapping) < 0.86


def test_specs_are_reproducible(cfg, catalogue):
    cfg["population"]["count"] = 5
    assert build_specs(cfg, catalogue) == build_specs(copy.deepcopy(cfg), catalogue)
