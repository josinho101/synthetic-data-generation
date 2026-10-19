import random

from sdg_humans.clothing_match import matches, pick

CANDIDATES = [{"name": n, "path": f"/x/{n}.mhclo", "pack": None}
              for n in ("male_casualsuit_pants", "female_skirt01", "wool_socks", "jeans01", "tshirt02")]


def test_include_and_exclude():
    slot = {"include_any": "pants,jeans", "exclude": "jeans"}
    assert matches("male_casualsuit_pants", slot, "male")
    assert not matches("jeans01", slot, "male")


def test_sex_specific_keywords():
    slot = {"include_female": "skirt"}
    assert matches("female_skirt01", slot, "female")
    assert not matches("female_skirt01", slot, "male")


def test_empty_include_matches_nothing():
    assert not matches("anything", {}, "male")


def test_pick_is_reproducible_and_respects_chance():
    slot = {"include_any": "sock", "chance": 100}
    assert pick(CANDIDATES, slot, "male", random.Random(1))["name"] == "wool_socks"
    assert pick(CANDIDATES, {"include_any": "sock", "chance": 0}, "male", random.Random(1)) is None
