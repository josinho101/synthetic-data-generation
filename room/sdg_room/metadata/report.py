"""Run-level reports: rooms.csv, summary.json (configured vs achieved), contact_sheet.png (floor plans)."""

import csv
import json
import math
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

CATEGORICAL = ["wall_finish", "floor_material", "detector_side", "changing_room_corner", "entrance_wall",
               "changing_door_wall", "cct_class", "patient_support", "tube_column_type"]


def write_rooms_csv(path, specs: list, results: dict) -> None:
    cols = ["id", "status", "seed", "attempt", "length_m", "width_m", "ceiling_height_m"] + CATEGORICAL + [
        "entrance_placed_on", "cct_k", "lux_target", "lux_estimated", "panel_size", "panels", "sid_m",
        "detector_center_height_m", "detector_x_m", "support_placed", "props_placed", "props_dropped", "cameras", "cov_marker", "cov_walk_body",
        "cov_walk_feet", "cov_support", "cov_room", "usd"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=cols)
        writer.writeheader()
        for spec in specs:
            lay, res = spec["layout"], results.get(spec["id"], {})
            eq = lay["equipment"]
            row = {k: spec.get(k) for k in CATEGORICAL}
            row.update(id=spec["id"], status=res.get("status", "pending"), seed=spec["seed"], attempt=spec["attempt"],
                       length_m=spec["footprint_m"][0], width_m=spec["footprint_m"][1],
                       ceiling_height_m=spec["ceiling_height_m"], entrance_placed_on=lay["entrance"]["placed_on"],
                       cct_k=spec["cct_k"], lux_target=spec["lux_target"],
                       lux_estimated=round(res.get("lux_estimated", 0.0), 1), panel_size=spec["panel_size"],
                       panels=sum(1 for p in lay["panels"] if p["zone"] == "exam"), sid_m=eq["sid_m"],
                       detector_center_height_m=eq["detector"]["center"][2], detector_x_m=round(eq["detector"]["center"][0], 3),
                       support_placed=(lay.get("patient_support") or {}).get("kind", "none"),
                       props_placed=";".join(p["name"] for p in lay.get("props", [])),
                       props_dropped=";".join(lay.get("dropped", [])),
                       cameras=";".join(c["name"] for c in spec.get("cameras", [])), usd=res.get("usd", ""),
                       **{f"cov_{k}": (spec.get("camera_coverage") or {}).get(g, "")
                          for k, g in (("marker", "marker"), ("walk_body", "walk_path"), ("walk_feet", "walk_feet"),
                                       ("support", "support"), ("room", "room"))})
            writer.writerow(row)


def write_summary(path, cfg: dict, specs: list, results: dict, timings: dict) -> dict:
    var, total = cfg["variations"], len(specs)
    distributions = {}
    for key in CATEGORICAL:
        weights = var[key]
        wsum = sum(weights.values()) or 1.0
        achieved = Counter(s[key] for s in specs)
        distributions[key] = {k: {"configured_pct": round(100.0 * w / wsum, 1), "achieved": achieved.get(k, 0),
                                  "achieved_pct": round(100.0 * achieved.get(k, 0) / total, 1) if total else 0.0}
                              for k, w in weights.items()}
    lux = [s["lux_target"] for s in specs]
    status = Counter(r.get("status", "pending") for r in results.values())
    summary = {
        "rooms": total, "status": dict(status),
        "failed": sorted(rid for rid, r in results.items() if r.get("status") == "failed"),
        "distributions": distributions,
        "lux_target": {"mean": round(sum(lux) / total, 1) if total else 0, "min": min(lux, default=0),
                       "max": max(lux, default=0)},
        "props_dropped": dict(Counter(n.rsplit("_", 1)[0] for s in specs for n in s["layout"].get("dropped", []))),
        "layout_rejections": sum(len(s.get("layout_rejections", [])) for s in specs),
        "timings_s": timings,
    }
    Path(path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def contact_sheet(run_dir, ids: list, out_path, columns: int = 4, thumb_w: int = 480) -> bool:
    images = []
    for rid in ids:
        p = Path(run_dir) / "rooms" / rid / f"{rid}_plan.png"
        if p.exists():
            images.append((rid, Image.open(p).convert("RGB")))
    if not images:
        return False
    thumbs = []
    for rid, img in images:
        h = int(img.height * thumb_w / img.width)
        thumbs.append((rid, img.resize((thumb_w, h))))
    th = max(t.height for _, t in thumbs)
    cols = max(1, min(columns, len(thumbs)))
    rows = math.ceil(len(thumbs) / cols)
    sheet = Image.new("RGB", (cols * thumb_w, rows * (th + 22)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for k, (rid, t) in enumerate(thumbs):
        x, y = (k % cols) * thumb_w, (k // cols) * (th + 22)
        sheet.paste(t, (x, y + 22))
        d.text((x + 6, y + 4), rid, fill=(20, 20, 20))
    sheet.save(out_path)
    return True
