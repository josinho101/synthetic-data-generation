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


def test_resolve_slot_per_sex_and_one_of():
    import random
    from sdg_humans.clothing_match import leaf_slots, resolve_slot
    slot = {"male": {"mpfb_slot": {"include_male": "jeans"}},
            "female": {"one_of": [{"weight": 1, "asset": "skirt.mhclo", "recolor": "skirt"},
                                  {"weight": 0, "mpfb_slot": {"include_female": "jeans"}}]}}
    rng = random.Random(1)
    assert resolve_slot(slot, "male", rng) == {"mpfb_slot": {"include_male": "jeans"}}
    assert resolve_slot(slot, "female", rng) == {"asset": "skirt.mhclo", "recolor": "skirt"}
    assert resolve_slot({"female": {"asset": "skirt.mhclo"}}, "male", rng) is None
    assert len(leaf_slots(slot)) == 3


def test_config_garments_match_the_sex():
    import random
    from sdg_humans.clothing_match import resolve_slot
    from sdg_humans.config import load_config
    cfg = load_config("configs")
    catalog = cfg["garment_catalog"]["garments"]
    rng = random.Random(7)
    seen = {"male": set(), "female": set()}
    for _ in range(50):
        for variant in cfg["clothing"]["variants"].values():
            for slot in variant["slots"].values():
                for sex in seen:
                    leaf = resolve_slot(slot, sex, rng)
                    if leaf and "garment" in leaf:
                        assert catalog[leaf["garment"]]["sex"] in (sex, "any"), (sex, leaf)
                        seen[sex].add(leaf["garment"])
    assert {"F01", "U07", "L03", "S01"} <= seen["male"] and {"F11", "U14", "L04", "S02"} <= seen["female"]


def test_catalog_asset_lookup():
    from sdg_humans.clothing_match import catalog_asset
    catalog = {"garments": {"L06": {"asset": "mindfront_male_trousers_1"}}}
    assert catalog_asset(catalog, "L06") == "mindfront_male_trousers_1"
    assert catalog_asset(catalog, "L99") is None and catalog_asset(None, "L06") is None
