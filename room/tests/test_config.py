import pytest

from sdg_room.config import ConfigError, apply_overrides, parse_set_args
from sdg_room.config.schema import footprint_m, max_sid, validate


def test_default_config_is_valid(cfg):
    assert validate(cfg) == []


def test_default_footprint_is_17_7_by_8_3_ft(cfg):
    length, width = footprint_m(cfg["room"])
    assert length == pytest.approx(17.7 * 0.3048)
    assert width == pytest.approx(8.3 * 0.3048)


def test_footprint_m_overrides_feet(cfg):
    bad = apply_overrides(cfg, {"room.footprint_m": [6.0, 3.0]})
    assert footprint_m(bad["room"]) == [6.0, 3.0]


def test_set_args_parse_yaml_values():
    assert parse_set_args(["room.footprint_ft=[20, 10]", "export.workers=3"]) == {
        "room.footprint_ft": [20, 10], "export.workers": 3}
    with pytest.raises(ConfigError):
        parse_set_args(["no_equals_sign"])


@pytest.mark.parametrize("key,value,needle", [
    ("variations.detector_side", {"up": 1}, "unknown option"),
    ("variations.wall_finish", {"marble": 1}, "unknown option"),
    ("variations.count", 0, "count"),
    ("lighting.lux", {"mean": 50, "sd": 10, "min": 100, "max": 1000}, "lighting.lux"),
    ("equipment.tube_stand.sid_m", [2.4, 2.5], "does not fit"),
    ("materials.glare", "blinding", "glare"),
    ("room.footprint_ft", [8, 17], "length"),
])
def test_bad_values_are_rejected(cfg, key, value, needle):
    errors = validate(apply_overrides(cfg, {key: value}))
    assert any(needle in e for e in errors), errors


def test_max_sid_fits_default_room(cfg):
    width = footprint_m(cfg["room"])[1]
    assert cfg["equipment"]["tube_stand"]["sid_m"][0] <= max_sid(cfg["equipment"], width) <= width
