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


def test_garment_id_slots_are_validated(cfg):
    slots = cfg["clothing"]["variants"]["top_and_jeans"]["slots"]
    slots["lower_body"] = {"garment": "L06"}
    assert validate(cfg) == []
    slots["lower_body"] = {"garment": "Z99"}
    assert any("garment 'Z99' not in garment_catalog.yaml" in e for e in validate(cfg))


def test_garment_catalog_ids_are_unique_and_complete(cfg):
    garments = cfg["garment_catalog"]["garments"]
    assert len({g["asset"] for g in garments.values()}) == len(garments)
    for gid, entry in garments.items():
        assert gid[0] == {"upper": "U", "lower": "L", "full": "F", "shoes": "S", "hat": "H"}[entry["category"]]
        assert entry["sex"] in ("male", "female", "any") and entry["rating"] in ("A", "B", "C", "X", "?")
