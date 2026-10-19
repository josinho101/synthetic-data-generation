"""Per-human metadata JSON (stdlib only; written from inside Blender)."""

import json
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = 1


def build_metadata(spec: dict, run_id: str, build: dict, versions: dict) -> dict:
    """Merge the resolved spec (inputs) with what the build measured (outputs)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "id": spec["id"],
        "run_id": run_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "seed": spec["seed"],
        "identity": {
            "sex": spec["sex"],
            "age_years": spec["age_years"],
            "age_band": spec["age_band"],
            "ethnicity": spec["ethnicity"],
            "race_mix": spec["macros"]["race"],
            "somatotype": spec["somatotype"],
            "skin_tone_mst": spec["skin"]["tone_mst"],
            "skin_rgb_hex": spec["skin"]["rgb_hex"],
            "skin_albedo_hex": spec["skin"].get("albedo_hex"),
            "eye_color": spec["eyes"]["color"],
            "hair": spec["hair"],
            "uniqueness_distance": spec.get("uniqueness_distance"),
        },
        "mpfb_macros": spec["macros"] | {"height": build["fit"]["height_macro"]},
        "face_targets": spec["face_targets"],
        "body": {
            "target_height_cm": spec["target_height_cm"],
            "height_cm": build["fit"]["height_cm"],
            "weight_kg": build["fit"]["weight_kg"],
            "bmi": build["fit"]["bmi"],
            "volume_l": build["fit"]["volume_l"],
            "fit_ok": build["fit"]["fit_ok"],
            "footwear_lift_cm": build["fit"].get("footwear_lift_cm", 0.0),
        },
        "measurements_cm": build["measurements"],
        "appearance": {"skin": build["skin"], "body_parts": build["body_parts"]},
        "clothing": {"variant": spec["clothing_variant"], "gown_color": spec.get("gown_color"),
                     "items": build["clothing"]},
        "skeleton": build["skeleton"],
        "landmarks": build["landmarks"],
        "anatomy": {"bone_meshes": build.get("anatomy", []), "count": len(build.get("anatomy", []))},
        "files": build["files"],
        "warnings": build["warnings"],
        "notes": build.get("notes", []),
        "versions": versions,
    }


def write_metadata(path, metadata: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path
