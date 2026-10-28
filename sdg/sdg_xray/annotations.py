"""Anatomy annotations of the captured frames (pxr only: usd-core or Isaac's Python; PIL only for the overlay).

Points (configs/annotations.yaml) are fixed on a skeleton joint, so they follow the animated body:
  vertebrae  mid-point of each vertebra = bounding-box centre of its Z-Anatomy bone mesh (rigid to vertebra_<level>)
  landmarks  hip = greater trochanter, shoulder = acromion, from <id>.json -> anatomy.points_m

build_points() runs on the host and stores each point as an offset in its joint's bind frame. In Isaac, posed()
moves the offsets with the joints' animated world matrices; heights() gives cm above the floor for
annotations/<frame>.json, and project() / draw_overlay() draw them into the RGB images.
All matrices are Gf row-vector matrices (p_world = p_local * M), as in UsdSkel and Gf.Frustum.
"""

from .config import ConfigError

GROUPS = ("vertebrae", "hip", "shoulder")
SIDE_LABEL = {"left": "L", "right": "R"}
LABEL = {"hip": "Hip", "shoulder": "Sho"}


# ----------------------------------------------------------------------------------------------------------- config
def validate_annotations(ann: dict) -> list:
    errors = []
    if not isinstance(ann.get("vertebrae") or [], list):
        errors.append("annotations.vertebrae must be a list of levels (C1 ... L5)")
    if not isinstance(ann.get("ndigits", 1), int) or not 0 <= ann.get("ndigits", 1) <= 4:
        errors.append("annotations.ndigits must be an integer 0..4")
    for group, sides in (ann.get("landmarks") or {}).items():
        if group not in GROUPS:
            errors.append(f"annotations.landmarks.{group}: unknown group (allowed {', '.join(GROUPS[1:])})")
            continue
        for side, spec in (sides or {}).items():
            if side not in SIDE_LABEL or not isinstance(spec, dict) or not spec.get("point") or not spec.get("joint"):
                errors.append(f"annotations.landmarks.{group}.{side}: needs left/right with point and joint")
    overlay = ann.get("overlay") or {}
    known = {"enabled", "marker_radius_px", "font_size_px", "label_vertebrae", "frame_number", "colors"}
    errors += [f"annotations.overlay.{k}: unknown key" for k in overlay if k not in known]
    for key in ("marker_radius_px", "font_size_px"):
        if not isinstance(overlay.get(key, 1), (int, float)) or overlay.get(key, 1) <= 0:
            errors.append(f"annotations.overlay.{key} must be a number > 0")
    if overlay.get("label_vertebrae", "all") not in ("all", "every_2nd"):
        errors.append("annotations.overlay.label_vertebrae must be all or every_2nd")
    for name, rgb in (overlay.get("colors") or {}).items():
        if not (isinstance(rgb, list) and len(rgb) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in rgb)):
            errors.append(f"annotations.overlay.colors.{name} must be [r, g, b] with 0..255")
    return errors


# ----------------------------------------------------------------------------------------------------------- points
def build_points(usd_path, meta: dict, ann: dict) -> list:
    """[{group, name, label, joint, offset [x, y, z]}] for one human; [] when its rig has no vertebra bones.

    `offset` is the point in its joint's bind frame (metres). Raises ConfigError for a landmark or joint that is
    missing in a Z-Anatomy human."""
    from pxr import Gf, Usd, UsdGeom, UsdSkel

    stage = Usd.Stage.Open(str(usd_path))
    skel = next((UsdSkel.Skeleton(p) for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton)), None)
    if skel is None:
        raise ConfigError(f"{usd_path}: no skeleton")
    joints = [str(j) for j in skel.GetJointsAttr().Get()]
    bind = {j.split("/")[-1]: Gf.Matrix4d(m) for j, m in zip(joints, skel.GetBindTransformsAttr().Get())}
    prefix = ann.get("mesh_prefix", "bone_vertebra_")
    meshes = {p.GetName(): p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh) and p.GetName().startswith(prefix)}
    levels = list(ann.get("vertebrae") or [])
    if not levels or not all(f"vertebra_{lv}" in bind for lv in levels):
        return []                                     # not an anatomical rig (e.g. MPFB): no vertebra joints

    points = []
    for level in levels:
        mesh = meshes.get(f"{prefix}{level}")
        if mesh is None:
            raise ConfigError(f"{usd_path}: bone mesh {prefix}{level} not found")
        pts = UsdGeom.Mesh(mesh).GetPointsAttr().Get()
        geom = UsdSkel.BindingAPI(mesh).GetGeomBindTransformAttr().Get() or Gf.Matrix4d(1.0)
        rng = Gf.Range3d()
        for p in pts:
            rng.UnionWith(geom.Transform(Gf.Vec3d(p)))
        points.append(_point("vertebrae", level, level, f"vertebra_{level}", rng.GetMidpoint(), bind))
    anatomy = (meta.get("anatomy") or {}).get("points_m") or {}
    for group, sides in (ann.get("landmarks") or {}).items():
        for side, spec in sides.items():
            if spec["point"] not in anatomy:
                raise ConfigError(f"{usd_path}: anatomy.points_m.{spec['point']} missing in the human's metadata")
            points.append(_point(group, side, f"{LABEL.get(group, group)} {SIDE_LABEL[side]}", spec["joint"],
                                 Gf.Vec3d(*anatomy[spec["point"]]), bind))
    return points


def _point(group, name, label, joint, world, bind) -> dict:
    if joint not in bind:
        raise ConfigError(f"annotation joint {joint!r} is not in the skeleton")
    offset = bind[joint].GetInverse().Transform(world)
    return {"group": group, "name": name, "label": label, "joint": joint, "offset": [float(v) for v in offset]}


def joints_needed(points) -> list:
    return sorted({p["joint"] for p in points})


def posed(points, joint_world: dict) -> list:
    """World position (Gf.Vec3d, metres) of every point, from {joint leaf name: world Gf.Matrix4d}."""
    from pxr import Gf
    return [joint_world[p["joint"]].Transform(Gf.Vec3d(*p["offset"])) for p in points]


def heights(points, positions, floor_z: float = 0.0, ndigits: int = 1) -> dict:
    """{"vertebrae": {C1: cm, ...}, "hip": {left, right}, "shoulder": {left, right}} above the floor."""
    out = {}
    for p, pos in zip(points, positions):
        out.setdefault(p["group"], {})[p["name"]] = round((pos[2] - floor_z) * 100.0, ndigits)
    return out


def record(frame: int, time_s: float, state: dict, values: dict) -> dict:
    """Content of annotations/<frame>.json."""
    return {"frame": frame, "image": f"{frame:06d}", "time_s": round(time_s, 4), "step": state.get("step"),
            "op": state.get("op"), "projection": state.get("projection"), "fov_light": state.get("fov"),
            "units": "cm", "reference": "room floor (z = 0)",
            **{group: values.get(group, {}) for group in GROUPS}}


# ----------------------------------------------------------------------------------------------------------- overlay
def project(positions, view, proj, width: int, height: int) -> list:
    """[(x px, y px, in_front)] of world points for a camera (Gf.Frustum ComputeViewMatrix and
    ComputeProjectionMatrix: row-vector 4x4 matrices). Pixel (0, 0) is the top-left corner."""
    from pxr import Gf
    view, proj = Gf.Matrix4d(view), Gf.Matrix4d(proj)
    out = []
    for p in positions:
        cam = Gf.Vec4d(p[0], p[1], p[2], 1.0) * view
        clip = cam * proj
        if cam[2] >= 0 or abs(clip[3]) < 1e-12:      # the camera looks along its -Z
            out.append((0.0, 0.0, False))
            continue
        nx, ny = clip[0] / clip[3], clip[1] / clip[3]
        out.append(((nx + 1.0) * 0.5 * width, (1.0 - ny) * 0.5 * height, True))
    return out


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                 # Pillow < 10.1: fixed-size bitmap font
        return ImageFont.load_default()


def draw_overlay(img, points, pixels, values: dict, style: dict, frame: int):
    """Draw the points (dot + label + height in cm) and the frame number into a PIL image (in place).

    Labels never overlap. Vertebra labels alternate between a column left and a column right of the spine, stacked in
    order (a label pushed off its dot's height gets a thin leader line, and leader lines never cross); hip and
    shoulder labels go on the outer side (away from the spine in the image), moved further out past any label in
    the way."""
    from PIL import ImageDraw
    scale = img.height / 720.0
    radius = max(1, round(float(style.get("marker_radius_px", 4)) * scale))
    font = _font(max(8, round(float(style.get("font_size_px", 14)) * scale)))
    stroke = max(1, round(scale))
    colors = style.get("colors") or {}
    every_2nd = style.get("label_vertebrae", "all") == "every_2nd"
    draw = ImageDraw.Draw(img)
    gap = radius + 3

    def size(text):
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        return x1 - x0, y1 - y0, x0, y0

    def put(text, rgb, box, dot=None):
        w, h, x0, y0 = size(text)
        end = (box[2] if box[0] < dot[0] else box[0], (box[1] + box[3]) / 2.0) if dot else None
        if dot and (abs(end[1] - dot[1]) > 0.5 or abs(end[0] - dot[0]) > gap + 1):   # moved: leader line
            draw.line([dot, end], fill=rgb, width=1)
        draw.text((box[0] - x0, box[1] - y0), text, fill=rgb, font=font, stroke_width=stroke, stroke_fill=(0, 0, 0))
        taken.append(box)

    def label(p):
        return f"{p['label']} {values.get(p['group'], {}).get(p['name'], '')}"

    visible = [(p, x, y) for p, (x, y, front) in zip(points, pixels)
               if front and 0 <= x < img.width and 0 <= y < img.height]

    taken = []                                          # label boxes already placed
    if style.get("frame_number", True):
        text = f"frame {frame:06d}"
        w, h, _, _ = size(text)
        x, y = round(8 * scale), round(8 * scale)
        put(text, tuple(colors.get("text", [255, 255, 255])), (x, y, x + w, y + h))

    # vertebrae: two columns, every other label on each side (in the configured order, top to bottom)
    spine = [(p, x, y) for p, x, y in visible if p["group"] == "vertebrae"]
    order = [p["name"] for p in points if p["group"] == "vertebrae"]
    columns = {True: [], False: []}
    for p, x, y in spine:
        nth = order.index(p["name"])
        if not (every_2nd and nth % 2):
            columns[nth % 2 == 1].append((p, x, y))
    for left, items in columns.items():
        if not items:
            continue
        items.sort(key=lambda it: it[2])
        h = max(size(label(p))[1] for p, _, _ in items) + 1
        ys, prev = [], -1e9
        for _, _, y in items:                            # stack downwards without overlap ...
            prev = max(y - h / 2.0, prev + h)
            ys.append(prev)
        shift = max(0.0, ys[-1] + h - img.height)         # ... and back up if the stack leaves the image
        ys = [max(0.0, v - shift) for v in ys]
        edge = min(x for _, x, _ in items) - gap if left else max(x for _, x, _ in items) + gap
        for (p, x, y), top in zip(items, ys):
            w = size(label(p))[0]
            put(label(p), tuple(colors.get("vertebrae", [255, 215, 0])),
                (edge - w, top, edge, top + h - 1) if left else (edge, top, edge + w, top + h - 1), (x, y))

    # hip / shoulder: beside the dot on the outer side, moved outwards past labels in the way, then up / down
    spine_x = sum(x for _, x, _ in spine) / len(spine) if spine else img.width / 2.0
    for p, x, y in visible:
        if p["group"] == "vertebrae":
            continue
        text, rgb = label(p), tuple(colors.get(p["group"], [255, 255, 0]))
        w, h, _, _ = size(text)
        outer_left = x < spine_x
        box = None
        for i in range(25):                              # 0, +1, -1, +2, -2, ... label heights
            dy = ((i + 1) // 2) * (h + 1) * (1 if i % 2 else -1)
            bx = x - gap - w if outer_left else x + gap
            for _ in range(len(taken) + 1):
                cand = (bx, y - h / 2.0 + dy, bx + w, y + h / 2.0 + dy)
                hit = next((t for t in taken if cand[0] < t[2] and t[0] < cand[2] and cand[1] < t[3] and t[1] < cand[3]),
                           None)
                if hit is None:
                    break
                bx = hit[0] - gap - w if outer_left else hit[2] + gap
            if hit is None and cand[0] >= 0 and cand[2] <= img.width and cand[1] >= 0 and cand[3] <= img.height:
                box = cand
                break
        if box:
            put(text, rgb, box, (x, y))
    for p, x, y in visible:                              # dots last: never hidden under a label
        rgb = tuple(colors.get(p["group"], [255, 255, 0]))
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=rgb, outline=(0, 0, 0))
    return img
