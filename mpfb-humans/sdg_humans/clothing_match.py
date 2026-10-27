"""Keyword matching for clothing slots (pure Python; mirrors MPFB's clothes-slot semantics).

A candidate matches when its name contains any `include_any` keyword or any keyword of
the sex-specific list (`include_male` / `include_female`), and none of `exclude`.
Empty include lists match nothing. Optional `pack` restricts to assets of that pack.
"""

import random


def _keywords(value) -> list:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    return [k.strip().lower() for k in str(value).split(",") if k.strip()]


def matches(name: str, slot: dict, sex: str) -> bool:
    name = name.lower()
    include = _keywords(slot.get("include_any")) + _keywords(slot.get(f"include_{sex}"))
    if not include or not any(k in name for k in include):
        return False
    return not any(k in name for k in _keywords(slot.get("exclude")))


def pick(candidates: list, slot: dict, sex: str, rng: random.Random, pack_names=None, taken=()):
    """candidates: [{"name": str, "path": str, "pack": str|None}]. Returns one or None.

    Exactly one chance draw and one pick draw are consumed per call (reproducible).
    """
    chance_roll = rng.uniform(0, 100)
    pick_roll = rng.random()
    if chance_roll >= float(slot.get("chance", 100)):
        return None
    packs = set(_keywords(slot.get("pack"))) | set(p.lower() for p in (pack_names or []))
    pool = [c for c in candidates
            if matches(c["name"], slot, sex) and c["path"] not in taken
            and (not packs or str(c.get("pack") or "").lower() in packs)]
    if not pool:
        return None
    pool.sort(key=lambda c: c["name"])
    return pool[int(pick_roll * len(pool)) % len(pool)]


SEXES = ("male", "female")
NO_CLOTHING = "none"      # clothing variant of every human when clothing.enabled is false


def variant_pcts(clothing: dict) -> dict:
    """Clothing variant -> share in %; {NO_CLOTHING: 100} when clothing.enabled is false (unclothed humans)."""
    if not clothing.get("enabled", True):
        return {NO_CLOTHING: 100}
    return {k: v["pct"] for k, v in clothing["variants"].items()}


def catalog_asset(catalog: dict, garment_id: str):
    """Asset name of a garment_catalog.yaml ID (e.g. "L06" -> "mindfront_male_trousers_1"), None if unknown."""
    entry = ((catalog or {}).get("garments") or {}).get(str(garment_id))
    return entry.get("asset") if entry else None


def resolve_slot(slot: dict, sex: str, rng: random.Random):
    """Turn a configured slot into one concrete slot ({asset: ...}, {mpfb_slot: ...} or {garment: ID}, plus
    options such as `recolor`), or None when the slot does not apply to this sex.

    * `male:` / `female:` keys give a different slot per sex (a missing sex = no garment);
    * `one_of: [{weight: w, ...slot...}, ...]` picks one alternative by weight.
    Exactly one random draw is consumed per `one_of` level (reproducible)."""
    if slot is None:
        return None
    if any(k in slot for k in SEXES):
        return resolve_slot(slot.get(sex), sex, rng)
    if "one_of" in slot:
        options = slot["one_of"]
        roll = rng.random() * sum(float(o.get("weight", 1)) for o in options)
        for option in options:
            roll -= float(option.get("weight", 1))
            if roll <= 0:
                break
        return resolve_slot({k: v for k, v in option.items() if k != "weight"}, sex, rng)
    return slot


def leaf_slots(slot):
    """All concrete alternatives of a configured slot (for validation / preflight)."""
    if slot is None:
        return []
    if any(k in slot for k in SEXES):
        return [leaf for sex in SEXES for leaf in leaf_slots(slot.get(sex))]
    if "one_of" in slot:
        return [leaf for option in slot["one_of"] for leaf in leaf_slots(option)]
    return [slot]
