import pytest

from anny_humans.config import ConfigError, load_config
from anny_humans.config.schema import effective_age_bands, validate

from conftest import ROOT


def test_default_config_is_valid(cfg):
    assert validate(cfg) == []
    assert cfg["population"]["age_range"] == {"min": 18, "max": 70}


@pytest.mark.parametrize("age_range, message", [
    ({"min": 17, "max": 70}, "age_range.min: must be >= 18"),
    ({"min": 18, "max": 71}, "age_range.max: must be <= 70"),
    ({"min": 40, "max": 40}, "min must be < max"),
    ({"min": 18.5, "max": 70}, "whole years"),
])
def test_age_range_limits(cfg, age_range, message):
    cfg["population"]["age_range"] = age_range
    assert any(message in e for e in validate(cfg))


def test_age_bands_are_clipped_to_the_range(cfg):
    pop = cfg["population"]
    pop["age_range"] = {"min": 25, "max": 60}
    assert effective_age_bands(pop) == pytest.approx({"25-30": 30.0, "31-50": 40.0, "51-60": 30.0})
    pop["age_range"] = {"min": 35, "max": 45}
    assert effective_age_bands(pop) == {"35-45": 100.0}


def test_band_outside_range_dropped_and_renormalised(cfg):
    pop = cfg["population"]
    pop["age_range"] = {"min": 40, "max": 70}
    bands = effective_age_bands(pop)
    assert set(bands) == {"40-50", "51-70"} and sum(bands.values()) == pytest.approx(100.0)


def test_no_overlapping_band_is_an_error(cfg):
    cfg["population"]["age_bands"] = {"18-30": 100}
    cfg["population"]["age_range"] = {"min": 40, "max": 70}
    assert any("no band overlaps" in e for e in validate(cfg))


def test_loader_applies_clipping_and_rejects_bad_ranges():
    cfg = load_config(ROOT / "configs", {"population.age_range.min": 30, "population.age_range.max": 50})
    bands = cfg["population"]["age_bands"]
    assert set(bands) == {"30-30", "31-50"} and sum(bands.values()) == pytest.approx(100.0)
    assert cfg["population"]["age_bands_configured"] == {"18-30": 30, "31-50": 40, "51-70": 30}
    with pytest.raises(ConfigError):
        load_config(ROOT / "configs", {"population.age_range.max": 75})


def test_only_office_clothing(cfg):
    assert set(cfg["clothing"]["variants"]) == {"shirt", "tshirt"}
    assert "gown_colors" not in cfg["clothing"]


def test_body_rig_and_topology(cfg):
    cfg["body"]["topology"] = "anny"
    assert any("body.topology" in e for e in validate(cfg))
