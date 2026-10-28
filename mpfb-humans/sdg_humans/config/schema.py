"""Validation rules for the configuration. Each check appends readable error strings."""

import re

from ..clothing_match import catalog_asset, leaf_slots

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _pct_block(errors, where, block, value_key=None):
    """Percent blocks are {name: pct} or {name: {pct: ...}} and must sum to 100."""
    if not isinstance(block, dict) or not block:
        errors.append(f"{where}: must be a non-empty mapping")
        return
    total = 0.0
    for name, value in block.items():
        pct = value.get(value_key) if (value_key and isinstance(value, dict)) else value
        if not isinstance(pct, (int, float)) or pct < 0:
            errors.append(f"{where}.{name}: percentage must be a number >= 0 (got {pct!r})")
            continue
        total += pct
    if abs(total - 100.0) > 1e-6:
        errors.append(f"{where}: percentages must sum to 100 (got {total:g})")


def _range(errors, where, value, lo=0.0, hi=1.0):
    ok = isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)
    if not ok or not (lo <= value[0] <= value[1] <= hi):
        errors.append(f"{where}: must be [min, max] with {lo} <= min <= max <= {hi} (got {value!r})")


def _validate_population(errors, pop, appearance):
    if not isinstance(pop.get("count"), int) or pop["count"] < 1:
        errors.append("population.count: must be an integer >= 1")
    if not isinstance(pop.get("seed"), int):
        errors.append("population.seed: must be an integer")
    _pct_block(errors, "population.sex", pop.get("sex"))
    for sex in (pop.get("sex") or {}):
        if sex not in ("male", "female"):
            errors.append(f"population.sex.{sex}: only 'male' and 'female' are supported")
        _range(errors, f"population.gender_macro.{sex}", (pop.get("gender_macro") or {}).get(sex))
    _pct_block(errors, "population.age_bands", pop.get("age_bands"))
    for band in (pop.get("age_bands") or {}):
        m = re.match(r"^(\d+)-(\d+)$", str(band))
        if not m or int(m.group(1)) > int(m.group(2)):
            errors.append(f"population.age_bands.{band}: band must look like '18-30'")
    _pct_block(errors, "population.ethnicity", pop.get("ethnicity"))
    profiles = (appearance or {}).get("ethnicity_profiles") or {}
    for eth in (pop.get("ethnicity") or {}):
        if eth not in profiles:
            errors.append(f"population.ethnicity.{eth}: no profile in appearance.ethnicity_profiles")
    _pct_block(errors, "population.somatotype", pop.get("somatotype"), "pct")
    for name, spec in (pop.get("somatotype") or {}).items():
        for macro in ("weight", "muscle", "proportions"):
            _range(errors, f"population.somatotype.{name}.{macro}", (spec or {}).get(macro))
    height = pop.get("height_cm") or {}
    for sex in (pop.get("sex") or {}):
        h = height.get(sex) or {}
        if not all(isinstance(h.get(k), (int, float)) for k in ("mean", "sd", "min", "max")):
            errors.append(f"population.height_cm.{sex}: needs mean, sd, min, max")
        elif not (h["min"] <= h["mean"] <= h["max"]) or h["sd"] <= 0:
            errors.append(f"population.height_cm.{sex}: require min <= mean <= max and sd > 0")
    order = pop.get("stratify_order") or []
    allowed = {"sex", "ethnicity", "age_bands", "somatotype", "clothing"}
    for item in order:
        if item not in allowed:
            errors.append(f"population.stratify_order: unknown stratum '{item}' (allowed {sorted(allowed)})")


def _validate_appearance(errors, app):
    tones = app.get("skin_tones_rgb") or {}
    for tone, rgb in tones.items():
        if not isinstance(rgb, str) or not _HEX.match(rgb):
            errors.append(f"appearance.skin_tones_rgb.{tone}: must be '#rrggbb'")
    for eth, prof in (app.get("ethnicity_profiles") or {}).items():
        mix = (prof or {}).get("race_mix") or {}
        if set(mix) != {"asian", "caucasian", "african"}:
            errors.append(f"appearance.ethnicity_profiles.{eth}.race_mix: needs asian, caucasian, african")
        for tone in ((prof or {}).get("skin_tone_weights") or {}):
            if tone not in tones:
                errors.append(f"appearance.ethnicity_profiles.{eth}: skin tone {tone} not in skin_tones_rgb")
    albedo = app.get("skin_albedo_lab") or {}
    for tone in tones:
        lab = albedo.get(tone)
        if not (isinstance(lab, (list, tuple)) and len(lab) == 3 and 0 < float(lab[0]) <= 100):
            errors.append(f"appearance.skin_albedo_lab.{tone}: must be [L*, a*, b*] with 0 < L* <= 100")
    if (app.get("skin") or {}).get("source") not in ("auto", "layered", "mhmat"):
        errors.append("appearance.skin.source: must be auto | layered | mhmat")
    for section, triple in ((app.get("face") or {}).get("sections") or {}).items():
        if not (isinstance(triple, list) and len(triple) == 3 and triple[0] <= triple[1]):
            errors.append(f"appearance.face.sections.{section}: must be [min_picks, max_picks, deviation]")
    _pct_block(errors, "appearance.eyes.colors", (app.get("eyes") or {}).get("colors"))


def _validate_clothing(errors, clothing, catalog=None):
    if not isinstance(clothing.get("enabled", True), bool):
        errors.append("clothing.enabled: must be true | false")
    _pct_block(errors, "clothing.variants", clothing.get("variants"), "pct")
    for name, var in (clothing.get("variants") or {}).items():
        for slot, spec in ((var or {}).get("slots") or {}).items():
            leaves = leaf_slots(spec) if isinstance(spec, dict) else [None]
            if not leaves or any(not isinstance(leaf, dict) or len({"asset", "mpfb_slot", "garment"} & set(leaf)) != 1
                                 for leaf in leaves):
                errors.append(f"clothing.variants.{name}.slots.{slot}: every alternative needs exactly one of "
                              "asset / mpfb_slot / garment")
            for leaf in leaves:
                if isinstance(leaf, dict) and "garment" in leaf and not catalog_asset(catalog, leaf["garment"]):
                    errors.append(f"clothing.variants.{name}.slots.{slot}: garment '{leaf['garment']}' "
                                  "not in garment_catalog.yaml")
            for leaf in leaves:
                if isinstance(leaf, dict) and leaf.get("recolor") and leaf["recolor"] not in (clothing.get("garment_colors") or {}):
                    errors.append(f"clothing.variants.{name}.slots.{slot}: recolor '{leaf['recolor']}' "
                                  "not in clothing.garment_colors")
    _pct_block(errors, "clothing.gown_colors", clothing.get("gown_colors"), "pct")
    if clothing.get("fallback_if_missing") not in ("skip_slot", "error"):
        errors.append("clothing.fallback_if_missing: must be skip_slot | error")
    fallback = clothing.get("fallback_variant")
    if fallback and fallback not in (clothing.get("variants") or {}):
        errors.append(f"clothing.fallback_variant: '{fallback}' is not a defined variant")


def _validate_landmarks(errors, lm):
    spine = lm.get("spine") or {}
    levels = spine.get("levels") or []
    for level in levels:
        if level not in (spine.get("segment_ratios") or {}):
            errors.append(f"landmarks.spine.segment_ratios: missing ratio for {level}")
    anchors = lm.get("anchors") or {}
    for level, anchor in (spine.get("pins") or {}).items():
        if level not in levels:
            errors.append(f"landmarks.spine.pins.{level}: not a spine level")
        if anchor not in anchors:
            errors.append(f"landmarks.spine.pins.{level}: anchor '{anchor}' not in anchors")
    for key in ("top_anchor", "bottom_anchor"):
        if spine.get(key) not in anchors:
            errors.append(f"landmarks.spine.{key}: '{spine.get(key)}' not in anchors")
    regions = {str(level)[0] for level in levels}
    depth = spine.get("internal_depth") or {}
    for region in sorted(regions):
        rule = depth.get(region)
        if not isinstance(rule, dict) or len({"fraction", "fixed_cm"} & set(rule)) != 1:
            errors.append(f"landmarks.spine.internal_depth.{region}: needs exactly one of fraction / fixed_cm")


def _validate_export(errors, export):
    for key in ("output_root", "blender_bin"):
        if not isinstance(export.get(key), str) or not export.get(key):
            errors.append(f"export.{key}: required")
    if not isinstance(export.get("workers"), int) or export["workers"] < 1:
        errors.append("export.workers: must be an integer >= 1")
    if not isinstance(export.get("install_missing_packs", False), bool):
        errors.append("export.install_missing_packs: must be true | false")
    for i, pack in enumerate(export.get("asset_packs") or []):
        if not isinstance(pack, dict) or not all(pack.get(k) for k in ("name", "file", "license")):
            errors.append(f"export.asset_packs[{i}]: needs name, file and license")
    if export.get("asset_mode") not in ("auto", "required"):
        errors.append("export.asset_mode: must be auto | required")
    if (export.get("usd") or {}).get("file_format") not in ("usd", "usda", "usdc"):
        errors.append("export.usd.file_format: must be usd | usda | usdc")


def _validate_anatomy(errors, anatomy):
    known = {"skull", "vertebrae", "ribs", "sternum", "shoulder_girdle", "pelvis", "limbs", "hands_feet"}
    for part in anatomy.get("parts") or []:
        if part not in known:
            errors.append(f"anatomy.parts: unknown part '{part}' (allowed {sorted(known)})")
    for key in ("rib_anterior_drop_cm", "rib_end_angle_deg"):
        if len(anatomy.get(key) or []) != 12:
            errors.append(f"anatomy.{key}: needs 12 values (ribs 1-12)")


def _validate_skeleton(errors, skel):
    from ..skeleton import LAYERS
    layer = skel.get("layer", "procedural")
    if layer not in LAYERS:
        errors.append(f"skeleton.layer: unknown layer '{layer}' (allowed {sorted(LAYERS)})")
    za = skel.get("zanatomy") or {}
    if layer == "zanatomy":
        if not isinstance(za.get("iters", 300), int) or za.get("iters", 300) < 1:
            errors.append("skeleton.zanatomy.iters: must be an integer >= 1")
        for key, hi in (("length_bound", 1.0), ("breadth_bound", 1.0)):
            v = za.get(key, 0.25)
            if not isinstance(v, (int, float)) or not 0 < v <= hi:
                errors.append(f"skeleton.zanatomy.{key}: must be in (0, {hi}]")
        ramp = za.get("contain_ramp", [100, 150])
        if not (isinstance(ramp, list) and len(ramp) == 2 and 0 <= ramp[0] <= ramp[1]):
            errors.append("skeleton.zanatomy.contain_ramp: must be [start, end] iterations with start <= end")
        for k, v in (za.get("weights") or {}).items():
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"skeleton.zanatomy.weights.{k}: must be a number >= 0")
        if za.get("max_influences", 4) not in (1, 2, 3, 4, 5, 6, 7, 8):
            errors.append("skeleton.zanatomy.max_influences: must be 1..8")


def validate(cfg: dict) -> list:
    """Return a list of human-readable errors (empty when the config is valid)."""
    errors = []
    _validate_population(errors, cfg.get("population") or {}, cfg.get("appearance"))
    _validate_appearance(errors, cfg.get("appearance") or {})
    _validate_clothing(errors, cfg.get("clothing") or {}, cfg.get("garment_catalog") or {})
    _validate_landmarks(errors, cfg.get("landmarks") or {})
    _validate_export(errors, cfg.get("export") or {})
    _validate_anatomy(errors, cfg.get("anatomy") or {})
    _validate_skeleton(errors, cfg.get("skeleton") or {})
    if not isinstance((cfg.get("logging") or {}).get("dict_config"), dict):
        errors.append("logging.dict_config: required (logging.config.dictConfig mapping)")
    return errors
