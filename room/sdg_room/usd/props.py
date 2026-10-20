"""Clutter and optional elements: chairs, lead-apron rack, lead screen, cabinet, bin, stool, table, stretcher,
cable runs. Local frame of every item: origin = centre of its floor footprint, +Y = its front (away from a wall)."""

import math

from ..layout.geometry import Rect
from .stage import safe_name

LABELS = {"chair": "chair", "apron_rack": "lead_apron", "lead_screen": "lead_screen",
          "generator_cabinet": "cabinet", "waste_bin": "waste_bin", "step_stool": "step_stool",
          "table": "table", "stretcher": "stretcher"}


def _chair(ctx, p, sx, sy, sz, color):
    seat, metal = ctx.looks.color(color, 0.55, clearcoat=0.2), ctx.looks.get("Metal")
    seat_h = 0.46
    ctx.box(p, "Seat", (sx, sy * 0.9, 0.05), (0, 0.02, seat_h), seat)
    ctx.box(p, "Back", (sx, 0.04, sz - seat_h - 0.05), (0, -sy / 2 + 0.03, (sz + seat_h) / 2 + 0.02), seat)
    for k, (x, y) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        ctx.cyl(p, f"Leg{k}", 0.012, seat_h - 0.025, "z", (x * (sx / 2 - 0.03), y * (sy / 2 - 0.04), (seat_h - 0.025) / 2), metal)


def _apron_rack(ctx, p, sx, sy, sz, color, aprons):
    metal = ctx.looks.get("Metal")
    rail_z = sz - 0.1
    ctx.box(p, "WallBoard", (sx, 0.02, 0.14), (0, -sy / 2 + 0.01, rail_z), ctx.looks.color(color if not aprons else "#d8dadc", 0.5))
    n = max(len(aprons), 1)
    apron_w, apron_h = min(0.55, sx - 0.05), 0.95
    for k, apron_color in enumerate(aprons):
        x = -sx / 2 + apron_w / 2 + (sx - apron_w) * (k / (n - 1) if n > 1 else 0.5)
        y = -sy / 2 + 0.035 + k * 0.022
        ctx.cyl(p, f"Arm{k}", 0.008, 0.10, "y", (x, -sy / 2 + 0.06, rail_z), metal, collide=False)
        apron = ctx.box(p, f"Apron_{k + 1:02d}", (apron_w, 0.02, apron_h), (x, y + 0.02, rail_z - 0.02 - apron_h / 2),
                        ctx.looks.color(apron_color, 0.65, clearcoat=0.1))
        ctx.label(apron.GetPrim(), "lead_apron")


def _lead_screen(ctx, p, sx, sy, sz, color):
    body, metal = ctx.looks.color(color, 0.4, clearcoat=0.4), ctx.looks.get("Metal")
    glass = ctx.looks.make("LeadGlass", color="#9fb8b0", roughness=0.05, opacity=0.35, ior=1.6)
    for k, x in enumerate((-sx / 2 + 0.05, sx / 2 - 0.05)):
        ctx.box(p, f"Foot{k}", (0.06, sy, 0.04), (x, 0, 0.06), metal)
        for j, y in enumerate((-sy / 2 + 0.04, sy / 2 - 0.04)):
            ctx.cyl(p, f"Caster{k}{j}", 0.035, 0.03, "x", (x, y, 0.035), ctx.looks.color("#2a2a2a", 0.7))
    panel_h = sz - 0.62
    ctx.box(p, "Panel", (sx, 0.05, panel_h), (0, 0, 0.12 + panel_h / 2), body)
    ctx.box(p, "Window", (sx - 0.12, 0.03, 0.40), (0, 0, sz - 0.25), glass)
    ctx.box(p, "FrameTop", (sx, 0.06, 0.05), (0, 0, sz - 0.025), body)
    for k, x in enumerate((-sx / 2 + 0.03, sx / 2 - 0.03)):
        ctx.box(p, f"FrameSide{k}", (0.06, 0.06, 0.45), (x, 0, sz - 0.25), body)


def _cabinet(ctx, p, sx, sy, sz, color):
    body = ctx.looks.color(color, 0.45, clearcoat=0.3)
    accent = ctx.looks.get("EquipAccent")
    ctx.box(p, "Body", (sx, sy, sz), (0, 0, sz / 2), body)
    ctx.box(p, "FrontPanel", (sx - 0.08, 0.01, sz - 0.4), (0, sy / 2 + 0.005, sz / 2 - 0.05), accent, collide=False)
    ctx.box(p, "Display", (0.2, 0.012, 0.12), (0, sy / 2 + 0.006, sz - 0.15), ctx.looks.color("#1b2a33", 0.1), collide=False)


def _waste_bin(ctx, p, sx, sy, sz, color):
    body = ctx.looks.color(color, 0.5)
    ctx.cyl(p, "Body", sx / 2, sz - 0.02, "z", (0, 0, (sz - 0.02) / 2), body)
    ctx.cyl(p, "Lid", sx / 2 + 0.01, 0.02, "z", (0, 0, sz - 0.01), body)


def _step_stool(ctx, p, sx, sy, sz, color):
    body, tread = ctx.looks.color(color, 0.4, metallic=0.3), ctx.looks.color("#2b2b2b", 0.8)
    ctx.box(p, "Lower", (sx, sy, sz / 2), (0, 0, sz / 4), body)
    ctx.box(p, "Upper", (sx, sy / 2, sz / 2), (0, -sy / 4, sz * 0.75), body)
    ctx.box(p, "TreadLow", (sx - 0.04, sy / 2 - 0.04, 0.006), (0, sy / 4, sz / 2 + 0.003), tread, collide=False)
    ctx.box(p, "TreadHigh", (sx - 0.04, sy / 2 - 0.04, 0.006), (0, -sy / 4, sz + 0.003), tread, collide=False)


def _table(ctx, p, sx, sy, sz, color, pad_color):
    body, pad = ctx.looks.color(color, 0.4, clearcoat=0.3), ctx.looks.color(pad_color, 0.7)
    accent = ctx.looks.get("EquipAccent")
    ctx.box(p, "Base", (0.70, 0.50, 0.08), (0, 0, 0.04), accent)
    ctx.box(p, "Pedestal", (0.45, 0.35, sz - 0.18), (0, 0, 0.08 + (sz - 0.18) / 2), body)
    ctx.box(p, "Top", (sx, sy, 0.06), (0, 0, sz - 0.07), body)
    ctx.box(p, "Pad", (sx - 0.04, sy - 0.06, 0.04), (0, 0, sz - 0.02), pad)


def _stretcher(ctx, p, sx, sy, sz, color, pad_color):
    frame, pad, metal = ctx.looks.color(color, 0.35, metallic=0.4), ctx.looks.color(pad_color, 0.7), ctx.looks.get("Metal")
    deck = sz - 0.17
    ctx.box(p, "Base", (sx - 0.2, sy - 0.1, 0.06), (0, 0, 0.20), frame)
    for k, x in enumerate((-sx / 2 + 0.35, sx / 2 - 0.35)):
        ctx.box(p, f"Column{k}", (0.10, 0.10, deck - 0.23), (x, 0, 0.23 + (deck - 0.23) / 2), frame)
    ctx.box(p, "Deck", (sx, sy - 0.04, 0.05), (0, 0, deck), frame)
    ctx.box(p, "Mattress", (sx - 0.04, sy - 0.10, 0.10), (0, 0, deck + 0.075), pad)
    for k, (x, y) in enumerate(((-1, -1), (1, -1), (1, 1), (-1, 1))):
        ctx.cyl(p, f"Wheel{k}", 0.075, 0.04, "y", (x * (sx / 2 - 0.15), y * (sy / 2 - 0.08), 0.075),
                ctx.looks.color("#2a2a2a", 0.7))
    for k, y in enumerate((-sy / 2 + 0.01, sy / 2 - 0.01)):
        ctx.cyl(p, f"SideRail{k}", 0.012, sx * 0.6, "x", (0, y, deck + 0.22), metal)
        for j, x in enumerate((-sx * 0.28, sx * 0.28)):
            ctx.cyl(p, f"RailPost{k}{j}", 0.01, 0.20, "z", (x, y, deck + 0.12), metal, collide=False)
    ctx.cyl(p, "PushBar", 0.015, sy - 0.1, "y", (-sx / 2 + 0.02, 0, deck + 0.35), metal)


_BUILDERS = {"chair": _chair, "lead_screen": _lead_screen, "generator_cabinet": _cabinet, "waste_bin": _waste_bin,
             "step_stool": _step_stool}


def build_item(ctx, parent, item):
    """One placed item (layout entry) as <parent>/<Name> Xform at its footprint centre."""
    sx, sy, sz = item["size_m"]
    cx, cy = item["center"]
    kind = item["kind"]
    grp = ctx.group(f"{parent}/{safe_name(item['name'].title().replace('_', ''))}", translate=(cx, cy, 0),
                    rotate=(0, 0, item["yaw_deg"]), label=LABELS.get(kind, kind))
    p = str(grp.GetPath())
    if kind == "apron_rack":
        _apron_rack(ctx, p, sx, sy, sz, item["color"], item.get("aprons", []))
    elif kind in ("table", "stretcher"):
        (_table if kind == "table" else _stretcher)(ctx, p, sx, sy, sz, item["color"], item["pad_color"])
    else:
        _BUILDERS[kind](ctx, p, sx, sy, sz, item["color"])
    if kind not in ("apron_rack", "generator_cabinet"):
        ctx.rigid(grp.GetPrim())
    return p


def build_props(ctx):
    lay = ctx.spec["layout"]
    grp = ctx.group(f"{ctx.root}/Props")
    gp = str(grp.GetPath())
    paths = {}
    if lay.get("patient_support"):
        sup = dict(lay["patient_support"])
        sup["name"] = sup["kind"]
        paths[sup["kind"]] = build_item(ctx, gp, sup)
    for item in lay.get("props", []):
        paths[item["name"]] = build_item(ctx, gp, item)
    H = ctx.spec["ceiling_height_m"]
    pcfg = ctx.cfg["props"]["items"]["cable_runs"]
    for k, run in enumerate(lay.get("cable_runs", [])):
        mat = ctx.looks.color(run["color"], 0.6)
        name = f"CableRun_{k + 1:02d}"
        g = ctx.group(f"{gp}/{name}", label="cable")
        if run["type"] == "floor_cover":
            (x0, y0), (x1, y1) = run["points"]
            length = math.hypot(x1 - x0, y1 - y0)
            yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
            seg = ctx.group(f"{g.GetPath()}/Cover", translate=((x0 + x1) / 2, (y0 + y1) / 2, 0), rotate=(0, 0, yaw))
            ctx.box(str(seg.GetPath()), "Ramp", (length, pcfg["cover_width_m"], pcfg["cover_height_m"]),
                    (0, 0, pcfg["cover_height_m"] / 2), mat)
        else:
            r = Rect.from_list(run["rect"])
            ctx.box(str(g.GetPath()), "Conduit", (r.sx, r.sy, H), (r.cx, r.cy, H / 2), mat)
        paths[name] = str(g.GetPath())
    return paths
