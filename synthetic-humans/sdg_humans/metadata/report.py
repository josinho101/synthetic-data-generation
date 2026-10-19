"""Run-level reports: population.csv, summary.json and contact_sheet.png."""

import csv
import json
import logging
from collections import Counter
from pathlib import Path

_LOG = logging.getLogger("sdg_humans.report")

CSV_COLUMNS = [
    "id", "status", "sex", "age_years", "age_band", "ethnicity", "somatotype", "skin_tone_mst", "skin_rgb_hex",
    "eye_color", "clothing_variant", "gown_color", "target_height_cm", "height_cm", "weight_kg", "bmi", "fit_ok",
    "ear_height_left_cm", "ear_height_right_cm", "eye_height_cm", "c7_height_cm", "shoulder_height_left_cm",
    "jugular_notch_height_cm", "xiphoid_height_cm", "iliac_crest_height_cm", "chest_width_cm",
    "chest_ap_depth_cm", "biacromial_width_cm", "landmark_joints", "usd", "preview", "warnings",
]


def load_metadata(humans_dir: Path) -> list:
    rows = []
    for path in sorted(Path(humans_dir).glob("*/*.json")):
        if path.stem == path.parent.name:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def _row(meta: dict, status: str) -> dict:
    ident, body, meas = meta["identity"], meta["body"], meta["measurements_cm"]
    return {
        "id": meta["id"], "status": status, "sex": ident["sex"], "age_years": ident["age_years"],
        "age_band": ident["age_band"], "ethnicity": ident["ethnicity"], "somatotype": ident["somatotype"],
        "skin_tone_mst": ident["skin_tone_mst"], "skin_rgb_hex": ident["skin_rgb_hex"],
        "eye_color": ident["eye_color"], "clothing_variant": meta["clothing"]["variant"],
        "gown_color": meta["clothing"].get("gown_color"), "target_height_cm": body["target_height_cm"],
        "height_cm": body["height_cm"], "weight_kg": body["weight_kg"], "bmi": body["bmi"], "fit_ok": body["fit_ok"],
        **{k: meas.get(k) for k in CSV_COLUMNS if k.endswith("_cm") and k not in ("target_height_cm", "height_cm")},
        "landmark_joints": len(meta["landmarks"]), "usd": meta["files"]["usd"], "preview": meta["files"]["preview"],
        "warnings": " | ".join(meta.get("warnings", [])),
    }


def write_population_csv(path: Path, metadata: list, statuses: dict) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for meta in metadata:
            writer.writerow(_row(meta, statuses.get(meta["id"], "unknown")))


def distributions(cfg: dict, metadata: list) -> dict:
    pop = cfg["population"]
    configured = {
        "sex": pop["sex"], "ethnicity": pop["ethnicity"], "age_band": pop["age_bands"],
        "somatotype": {k: v["pct"] for k, v in pop["somatotype"].items()},
        "clothing_variant": {k: v["pct"] for k, v in cfg["clothing"]["variants"].items()},
    }
    getters = {
        "sex": lambda m: m["identity"]["sex"], "ethnicity": lambda m: m["identity"]["ethnicity"],
        "age_band": lambda m: m["identity"]["age_band"], "somatotype": lambda m: m["identity"]["somatotype"],
        "clothing_variant": lambda m: m["clothing"]["variant"],
    }
    return {name: {"configured_pct": configured[name], "achieved": dict(Counter(getters[name](m) for m in metadata))}
            for name in configured}


def _stats(values: list) -> dict:
    values = [v for v in values if isinstance(v, (int, float))]
    if not values:
        return {}
    return {"min": round(min(values), 2), "mean": round(sum(values) / len(values), 2), "max": round(max(values), 2)}


def write_summary(path: Path, cfg: dict, run_id: str, metadata: list, results: dict, elapsed_s: float) -> dict:
    by_status = Counter(r.get("status", "failed") for r in results.values())
    summary = {
        "run_id": run_id, "requested": len(results), "status_counts": dict(by_status), "elapsed_s": round(elapsed_s, 1),
        "failed": {hid: r.get("error") for hid, r in results.items() if r.get("status") == "failed"},
        "distributions": distributions(cfg, metadata),
        "body_stats": {key: _stats([m["body"][key] for m in metadata]) for key in ("height_cm", "weight_kg", "bmi")},
        "build_time_s": _stats([r.get("duration_s") for r in results.values()]),
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def write_contact_sheet(path: Path, humans_dir: Path, ids: list, columns: int = 8, tile_width: int = 256) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        _LOG.warning("pillow not installed - contact sheet skipped")
        return False
    tiles = []
    for hid in ids:
        png = Path(humans_dir) / hid / f"{hid}.png"
        if png.exists():
            img = Image.open(png).convert("RGB")
            img = img.resize((tile_width, int(img.height * tile_width / img.width)))
            ImageDraw.Draw(img).text((6, 6), hid, fill=(20, 20, 20))
            tiles.append(img)
    if not tiles:
        return False
    rows = (len(tiles) + columns - 1) // columns
    cols = min(columns, len(tiles))
    sheet = Image.new("RGB", (cols * tile_width, rows * tiles[0].height), (255, 255, 255))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, ((i % columns) * tile_width, (i // columns) * tiles[0].height))
    sheet.save(path)
    return True
