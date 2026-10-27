"""Build the manifest: N fully resolved human specs (no randomness left for the build)."""

import hashlib
import json
import logging
import random
from datetime import datetime
from pathlib import Path

from . import anthropometrics, ethnicity, face, identity, looks, somatotype
from ..config.schema import age_range
from .quotas import assign_strata

_LOG = logging.getLogger("anny_humans.sampling")

MANIFEST_VERSION = 1


def derive_seed(global_seed: int, index: int, attempt: int = 0) -> int:
    digest = hashlib.sha256(f"{global_seed}:{index}:{attempt}".encode()).hexdigest()
    return int(digest[:12], 16)


def _factors(cfg: dict) -> list:
    pop = cfg["population"]
    sources = {
        "sex": pop["sex"],
        "ethnicity": pop["ethnicity"],
        "age_bands": pop["age_bands"],
        "somatotype": {k: v["pct"] for k, v in pop["somatotype"].items()},
        "clothing": {k: v["pct"] for k, v in cfg["clothing"]["variants"].items()},
    }
    order = list(pop.get("stratify_order") or sources)
    order += [k for k in sources if k not in order]
    return [(name, sources[name]) for name in order]


def _sample_free(rng, cfg, strata, catalogue) -> dict:
    """Everything that is not fixed by the strata (re-drawn on uniqueness collisions)."""
    pop, app = cfg["population"], cfg["appearance"]
    sex, eth = strata["sex"], strata["ethnicity"]
    age_years = anthropometrics.sample_age_years(rng, strata["age_bands"], age_range(pop))
    macros = somatotype.sample_sex_macros(rng, pop, sex)
    macros.update(somatotype.sample_body_macros(rng, pop["somatotype"], strata["somatotype"]))
    macros["age"] = round(anthropometrics.age_to_anny(age_years, pop["age_years_to_anny"]), 4)
    macros["height"] = 0.5  # solved at build time to hit target_height_cm
    macros["race"] = ethnicity.sample_race_mix(rng, app["ethnicity_profiles"][eth])
    return {
        "age_years": age_years,
        "target_height_cm": anthropometrics.sample_height_cm(rng, pop["height_cm"], sex, eth),
        "macros": macros,
        "skin": ethnicity.sample_skin(rng, app, eth, sex, age_years),
        "face_targets": face.sample_face_targets(rng, app.get("face") or {}, catalogue),
        **looks.sample_looks(rng, app, cfg["clothing"], sex, age_years),
    }


def build_specs(cfg: dict, catalogue: dict) -> list:
    pop = cfg["population"]
    n, seed = int(pop["count"]), int(pop["seed"])
    strata_list = assign_strata(n, _factors(cfg), random.Random(seed))
    uniq = pop.get("uniqueness") or {}
    threshold = float(uniq.get("min_feature_distance", 0.0))
    max_resample = int(uniq.get("max_resample", 0))

    specs = []
    for index, strata in enumerate(strata_list):
        human_id = f"{pop.get('id_prefix', 'H')}{index + 1:0{int(pop.get('id_digits', 4))}d}"
        best, best_distance = None, -1.0
        for attempt in range(max_resample + 1):
            human_seed = derive_seed(seed, index, attempt)
            spec = {"id": human_id, "index": index, "seed": human_seed,
                    "sex": strata["sex"], "ethnicity": strata["ethnicity"],
                    "age_band": strata["age_bands"], "somatotype": strata["somatotype"],
                    "clothing_variant": strata["clothing"]}
            spec.update(_sample_free(random.Random(human_seed), cfg, strata, catalogue))
            distance = identity.min_distance(spec, specs)
            if distance > best_distance:
                best, best_distance = spec, distance
            if distance >= threshold:
                break
        if best_distance < threshold:
            _LOG.warning(f"{human_id}: uniqueness {best_distance:.3f} < {threshold} after {max_resample} resamples")
        best["uniqueness_distance"] = None if best_distance == float("inf") else round(best_distance, 4)
        specs.append(best)
        _LOG.debug(f"{human_id}: {best['sex']} {best['ethnicity']} {best['somatotype']} seed={best['seed']}")
    return specs


def write_manifest(path, run_id: str, cfg: dict, specs: list) -> None:
    payload = {
        "manifest_version": MANIFEST_VERSION,
        "run_id": run_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "seed": cfg["population"]["seed"],
        "count": len(specs),
        "humans": specs,
    }
    with open(Path(path), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def read_manifest(path) -> dict:
    with open(Path(path), "r", encoding="utf-8") as handle:
        return json.load(handle)
