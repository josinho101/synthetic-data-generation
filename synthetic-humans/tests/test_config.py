import pytest

from sdg_humans.config.loader import ConfigError, apply_overrides
from sdg_humans.config.schema import validate


def test_shipped_config_is_valid(cfg):
    assert validate(cfg) == []


def test_percentages_must_sum_to_100(cfg):
    cfg["population"]["sex"] = {"male": 60, "female": 50}
    assert any("sum to 100" in e for e in validate(cfg))


def test_unknown_ethnicity_profile(cfg):
    cfg["population"]["ethnicity"] = {"martian": 100}
    assert any("no profile" in e for e in validate(cfg))


def test_bad_somatotype_range(cfg):
    cfg["population"]["somatotype"]["ectomorph"]["weight"] = [0.8, 0.2]
    assert any("somatotype.ectomorph.weight" in e for e in validate(cfg))


def test_overrides_apply_dotted_keys(cfg):
    out = apply_overrides(cfg, {"population.count": 3, "export.workers": None})
    assert out["population"]["count"] == 3
    assert out["export"]["workers"] == cfg["export"]["workers"]


def test_config_error_lists_messages():
    with pytest.raises(ConfigError) as info:
        raise ConfigError(["a", "b"])
    assert "a" in str(info.value) and "b" in str(info.value)


def test_anatomy_config_validation(cfg):
    cfg["anatomy"]["parts"] = ["skull", "tail"]
    cfg["anatomy"]["rib_end_angle_deg"] = [10] * 11
    errors = validate(cfg)
    assert any("unknown part 'tail'" in e for e in errors)
    assert any("rib_end_angle_deg" in e for e in errors)
