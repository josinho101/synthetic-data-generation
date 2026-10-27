#!/usr/bin/env python3
"""Render every garment of configs/garment_catalog.yaml on a reference human (headless Blender) and build
labelled contact sheets, so the garment IDs and realism ratings can be checked visually.

    python scripts/garment_catalog.py                       # all garments -> <output_root>/../garment_catalog
    python scripts/garment_catalog.py --ids U14 L06 S01     # only these
    python scripts/garment_catalog.py --category shoes --out /tmp/cat

Output: tiles/<ID>_<sex>.png (front + side), catalog_<category>.png sheets, catalog.png (all), index.csv.
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdg_humans.config import ConfigError, load_config  # noqa: E402
from sdg_humans.logging_setup import setup_console_only  # noqa: E402
from sdg_humans.mpfb_locate import resolve_mpfb_data_dir  # noqa: E402
from sdg_humans.pipeline.blender_runner import run_task  # noqa: E402
from sdg_humans.sampling.face import load_target_catalogue  # noqa: E402
from sdg_humans.sampling.manifest import build_specs  # noqa: E402

CATEGORIES = ("upper", "lower", "full", "shoes", "hat")


def reference_specs(cfg: dict) -> dict:
    """First male and first female of a small seeded population (reproducible reference humans)."""
    cfg = dict(cfg, population=dict(cfg["population"], count=10))
    specs = build_specs(cfg, load_target_catalogue(resolve_mpfb_data_dir(cfg["export"].get("mpfb_data_dir", "auto"))))
    return {sex: next(s for s in specs if s["sex"] == sex) for sex in ("male", "female")}


def contact_sheet(path: Path, tiles: list, columns: int, tile_width: int = 320) -> None:
    """tiles: [(png path, label)] -> grid with the label above each tile."""
    from PIL import Image, ImageDraw

    images = []
    for png, label in tiles:
        img = Image.open(png).convert("RGB")
        img = img.resize((tile_width, int(img.height * tile_width / img.width)))
        canvas = Image.new("RGB", (tile_width, img.height + 22), (255, 255, 255))
        canvas.paste(img, (0, 22))
        ImageDraw.Draw(canvas).text((6, 5), label, fill=(20, 20, 20))
        images.append(canvas)
    cols = min(columns, len(images))
    rows = (len(images) + columns - 1) // columns
    sheet = Image.new("RGB", (cols * tile_width, rows * images[0].height), (255, 255, 255))
    for i, img in enumerate(images):
        sheet.paste(img, ((i % columns) * tile_width, (i // columns) * images[0].height))
    sheet.save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="configs")
    parser.add_argument("--ids", nargs="*", help="only these garment IDs")
    parser.add_argument("--category", choices=CATEGORIES)
    parser.add_argument("--out", help="output directory (default: <export.output_root>/../garment_catalog)")
    parser.add_argument("--columns", type=int, default=6)
    args = parser.parse_args()
    setup_console_only()
    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        print(f"[config] {exc}")
        return 2
    catalog = cfg["garment_catalog"]["garments"]
    garments = [dict(entry, id=gid) for gid, entry in catalog.items()
                if (not args.ids or gid in args.ids) and (not args.category or entry["category"] == args.category)]
    if not garments:
        print("[catalog] no garment selected")
        return 2
    out = Path(args.out) if args.out else Path(cfg["export"]["output_root"]).parent / "garment_catalog"
    out.mkdir(parents=True, exist_ok=True)

    print(f"[catalog] rendering {len(garments)} garments in headless Blender -> {out}")
    task_args = {"config": cfg, "specs": reference_specs(cfg), "garments": garments, "out_dir": str(out)}
    result = run_task(cfg["export"]["blender_bin"], "catalog", task_args, out / "catalog.log",
                      timeout_s=60 * len(garments) + 600, work_dir=out / "_work")
    if result.get("status") not in ("ok", "warn"):
        print(f"[catalog] FAILED: {result.get('error')} (log: {out / 'catalog.log'})")
        return 1
    tiles, failed = result["tiles"], result.get("failed", {})

    rows, everything = [], []
    for category in CATEGORIES:
        sheet = []
        for g in (g for g in garments if g["category"] == category):
            for sex in ("male", "female"):
                key = f"{g['id']}_{sex}"
                if key in tiles:
                    sheet.append((tiles[key], f"{g['id']} [{g['rating']}] {sex[0]}  {g['asset']}"))
                if key in tiles or key in failed:
                    rows.append({"id": g["id"], "sex": sex, "asset": g["asset"], "category": category,
                                 "rating": g["rating"], "maps": g.get("maps", ""), "tile": tiles.get(key, ""),
                                 "error": failed.get(key, "")})
        if sheet:
            contact_sheet(out / f"catalog_{category}.png", sheet, args.columns)
            everything += sheet
    if everything:
        contact_sheet(out / "catalog.png", everything, args.columns)
    with open(out / "index.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "sex", "asset", "category", "rating", "maps", "tile", "error"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"[catalog] {len(tiles)} tiles, {len(failed)} failed -> {out}")
    for key, error in failed.items():
        print(f"  {key}: {error}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
