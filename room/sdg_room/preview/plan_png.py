"""Top-down floor plan PNG of one room (QA): walls, doors, equipment, beam corridor, marker, props, lights."""

from PIL import Image, ImageDraw, ImageFont

from ..layout.geometry import Rect

_COLORS = {
    "floor": (246, 245, 240), "wall": (70, 74, 80), "partition": (110, 114, 120), "changing": (232, 238, 246),
    "door": (196, 140, 60), "swing": (240, 214, 170), "wall_stand": (40, 110, 200), "tube_stand": (200, 70, 50),
    "rail": (230, 170, 160), "corridor": (255, 236, 150), "marker": (200, 150, 0), "panel": (150, 200, 255),
    "prop": (120, 160, 120), "support": (150, 120, 190), "bench": (176, 138, 90), "cable": (60, 60, 60),
    "text": (30, 30, 30), "walk": (220, 60, 160),
}


def _font(size):
    for name in ("DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_plan(spec: dict, path, px_per_m: int = 160, wall_t: float = 0.12) -> None:
    L, W = spec["footprint_m"]
    lay = spec["layout"]
    pad_m = wall_t + 0.35
    x_min = min(0.0, Rect.from_list(lay["changing_room"]["block"]).x0)    # the check-in room lies at x < 0
    width, height = int((L - x_min + 2 * pad_m) * px_per_m), int((W + 2 * pad_m) * px_per_m) + 60
    img = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    font, small = _font(max(12, px_per_m // 9)), _font(max(10, px_per_m // 13))

    def P(x, y):   # room meters -> pixels (y up)
        return ((x - x_min + pad_m) * px_per_m, (W + pad_m - y) * px_per_m)

    def rect(r, fill, outline=None, w=1):
        r = r if isinstance(r, Rect) else Rect.from_list(r)
        (ax, ay), (bx, by) = P(r.x0, r.y1), P(r.x1, r.y0)
        d.rectangle([ax, ay, bx, by], fill=fill, outline=outline, width=w)

    def label(text, x, y, f=small):
        px, py = P(x, y)
        d.text((px, py), text, fill=_COLORS["text"], font=f, anchor="mm")

    rect(Rect(-wall_t, -wall_t, L + wall_t, W + wall_t), _COLORS["wall"])
    rect(Rect(0, 0, L, W), _COLORS["floor"])
    cr = lay["changing_room"]
    rect(cr["block"], _COLORS["wall"])
    rect(cr["interior"], _COLORS["changing"])
    for name, r in lay["keepouts"].items():
        if name == "beam_corridor":
            rect(r, _COLORS["corridor"] + (170,))
        elif name == "tube_rail":
            rect(r, _COLORS["rail"] + (150,))
        elif "swing" in name:
            rect(r, _COLORS["swing"] + (120,))
    # door openings (gap in the wall drawn in door colour)
    ent = lay["entrance"]                       # outer door of the check-in room
    cx, cy = ent["center"]
    half = ent["width"] / 2
    if ent["axis"] == "y":
        rect(Rect(ent["plane"][0], cy - half, ent["plane"][1], cy + half), _COLORS["door"])
        label("ENTRANCE", ent["plane"][0] - 0.05, cy - half - 0.12, f=small)
    else:
        rect(Rect(cx - half, ent["plane"][0], cx + half, ent["plane"][1]), _COLORS["door"])
        label("ENTRANCE", cx, ent["plane"][1] + 0.12 if ent["out_normal"][1] > 0 else ent["plane"][0] - 0.12, f=small)
    door = cr["door"]
    dx, dy = door["center"]
    half = door["width"] / 2
    if door["axis"] == "y":
        rect(Rect(door["plane"][0], dy - half, door["plane"][1], dy + half), _COLORS["door"])
    else:
        rect(Rect(dx - half, door["plane"][0], dx + half, door["plane"][1]), _COLORS["door"])
    it = Rect.from_list(cr["interior"])
    label("CHECK-IN", it.cx, it.cy + 0.15, f=font)
    rect(cr["bench"]["rect"], _COLORS["bench"])
    if cr.get("chair"):
        rect(cr["chair"]["rect"], _COLORS["prop"])

    eq = lay["equipment"]
    rect(eq["wall_stand"]["footprint"], _COLORS["wall_stand"])
    fp = Rect.from_list(eq["wall_stand"]["footprint"])
    label("WALL STAND", fp.cx, fp.cy)
    rect(eq["tube_stand"]["footprint"], _COLORS["tube_stand"])
    tp = Rect.from_list(eq["tube_stand"]["footprint"])
    label("TUBE", tp.cx, tp.cy)
    m = lay["marker"]
    rect(m["outline"], None, outline=_COLORS["marker"], w=3)
    sx, sy = m["stand_point"]
    px, py = P(sx, sy)
    d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=_COLORS["marker"])
    em = lay.get("entrance_marker")
    if em:
        rect(em["outline"], None, outline=_COLORS["marker"], w=3)
        px, py = P(*em["stand_point"])
        d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=_COLORS["marker"])
    for run in lay.get("cable_runs", []):
        if run["type"] == "floor_cover":
            d.line([P(*p) for p in run["points"]], fill=_COLORS["cable"], width=max(2, px_per_m // 16))
        else:
            rect(run["rect"], _COLORS["cable"])
    sup = lay.get("patient_support")
    if sup:
        rect(sup["rect"], _COLORS["support"])
        r = Rect.from_list(sup["rect"])
        label(sup["kind"].upper(), r.cx, r.cy)
    for prop in lay.get("props", []):
        rect(prop["rect"], _COLORS["prop"])
        r = Rect.from_list(prop["rect"])
        label(prop["kind"].replace("_", " "), r.cx, r.cy)
    import math
    for stand in (lay.get("exam_cameras") or {}).values():          # tripod leg spread
        r = Rect.from_list(stand["stand_rect"])
        (ax, ay), (bx, by) = P(r.x0, r.y1), P(r.x1, r.y0)
        d.ellipse([ax, ay, bx, by], fill=(60, 110, 210, 40), outline=(40, 80, 180, 220), width=2)
    for cam in spec.get("cameras", []):
        if cam["zone"] == "outside":
            continue
        (x, y, z), (tx, ty, tz) = cam["position"], cam["target"]
        exam = bool(cam.get("rig"))
        fov = cam["fov_h_deg"]                     # horizontal FOV (portrait optics are already swapped)
        a, half = math.atan2(ty - y, tx - x), math.radians(fov / 2)
        reach = 1.2 if not exam else max(0.35, min(1.2, math.hypot(tx - x, ty - y)))
        fill, edge, dot = ((60, 110, 210, 55), (40, 80, 180, 220), (30, 70, 170)) if exam else \
            ((80, 170, 90, 60), (40, 130, 60, 200), (30, 120, 50))
        if exam and math.hypot(tx - x, ty - y) < 0.3 * abs(tz - z):    # looking down: draw the floor footprint
            r = math.tan(math.radians(cam["fov_v_deg"] / 2)) * abs(tz - z) * 0.5
            cx_, cy_ = P(tx, ty)
            d.ellipse([cx_ - r * px_per_m, cy_ - r * px_per_m, cx_ + r * px_per_m, cy_ + r * px_per_m],
                      fill=fill, outline=edge)
        else:
            wedge = [P(x, y), P(x + reach * math.cos(a - half), y + reach * math.sin(a - half)),
                     P(x + reach * math.cos(a + half), y + reach * math.sin(a + half))]
            d.polygon(wedge, fill=fill, outline=edge)
        px, py = P(x, y)
        d.ellipse([px - 6, py - 6, px + 6, py + 6], fill=dot)
        label(cam["name"].replace("CeilingCam_", "").replace("RealSense_D455_", "D455 "), x + 0.25 * math.cos(a),
              y + 0.25 * math.sin(a) - 0.12)
    # viewer arrow: outside the entrance, pointing at the door (this side faces the viewer in Isaac Sim)
    ox, oy = {"west": (-1, 0), "south": (0, -1), "north": (0, 1), "east": (1, 0)}[ent["wall"]]
    tip = (ent["center"][0] + ox * (wall_t + 0.03), ent["center"][1] + oy * (wall_t + 0.03))
    tail = (tip[0] + ox * 0.28, tip[1] + oy * 0.28)
    d.line([P(*tail), P(*tip)], fill=(200, 30, 30), width=4)
    d.text(P(*tail), "VIEWER", fill=(200, 30, 30), font=small, anchor="mm")
    for panel in lay["panels"]:
        (x, y), (pw, ph) = panel["center"], panel["size_m"]
        rect(Rect.centered(x, y, pw, ph), None, outline=_COLORS["panel"] + (255,), w=2)
    title = (f"{spec['id']}  {L:.2f} x {W:.2f} m  ceiling {spec['ceiling_height_m']:.2f} m | walls {spec['wall_finish']} "
             f"| floor {spec['floor_material']} | {spec['cct_class']} {spec['cct_k']:.0f} K, {spec['lux_target']:.0f} lux "
             f"| detector {spec['detector_side']} | SID {eq['sid_m']:.2f} m")
    d.text((10, height - 45), title, fill=_COLORS["text"], font=font)
    img.save(path)
