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
