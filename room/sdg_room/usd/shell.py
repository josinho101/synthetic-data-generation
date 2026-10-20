"""Room shell: floor, outer walls, ceiling and doors of the X-ray room, and the check-in / changing room annex outside
its entrance-end wall (own floor, ceiling, walls, the outer entrance door and the connecting door)."""

import math

from ..layout.geometry import Rect
from . import props as props_mod

CEILING_T = 0.05
FLOOR_T = 0.05


def _split(lo, hi, openings, top):
    """Pieces of a wall along one axis around door openings: [(a, b, z0, z1)]."""
    pieces, cursor = [], lo
    for c, w, h in sorted(openings):
        a, b = c - w / 2, c + w / 2
        if a - cursor > 1e-4:
            pieces.append((cursor, a, 0.0, top))
        pieces.append((a, b, h, top))          # header above the door
        cursor = b
    if hi - cursor > 1e-4:
        pieces.append((cursor, hi, 0.0, top))
    return pieces


def _wall(ctx, parent, name, axis, lo, hi, n0, n1, openings, top, material, uv):
    """Wall slab running along `axis` from lo to hi, thickness n0..n1 across, split around openings."""
    for k, (a, b, z0, z1) in enumerate(_split(lo, hi, openings, top)):
        if axis == "x":
            size, center = (b - a, n1 - n0, z1 - z0), ((a + b) / 2, (n0 + n1) / 2, (z0 + z1) / 2)
        else:
            size, center = (n1 - n0, b - a, z1 - z0), ((n0 + n1) / 2, (a + b) / 2, (z0 + z1) / 2)
        ctx.box(parent, f"{name}_{k}", size, center, material, uv)


def _door(ctx, parent, name, axis, center_along, width, height, face, normal, hinge, angle_deg, wall_t, leaf_mat,
          frame_mat):
    """Door frame in the opening + leaf hinged on the `face` side, swung by `angle_deg` towards `normal`."""
    grp = ctx.group(f"{parent}/{name}", label="door")
    path = str(grp.GetPath())
    jamb, depth = 0.05, wall_t + 0.02
    mid_n = face - normal * wall_t / 2       # centre of the wall slab across its thickness
    for side, a in (("L", center_along - width / 2 - jamb / 2), ("R", center_along + width / 2 + jamb / 2)):
        if axis == "x":
            ctx.box(path, f"Jamb{side}", (jamb, depth, height + jamb), (a, mid_n, (height + jamb) / 2), frame_mat)
        else:
            ctx.box(path, f"Jamb{side}", (depth, jamb, height + jamb), (mid_n, a, (height + jamb) / 2), frame_mat)
    if axis == "x":
        ctx.box(path, "Head", (width + 2 * jamb, depth, jamb), (center_along, mid_n, height + jamb / 2), frame_mat)
    else:
        ctx.box(path, "Head", (depth, width + 2 * jamb, jamb), (mid_n, center_along, height + jamb / 2), frame_mat)
    # leaf: hinge at one jamb, on the swing-side face
    sign = -1 if hinge == "lo" else 1
    h_along = center_along + sign * width / 2
    closed_dir = (-sign, 0.0) if axis == "x" else (0.0, -sign)
    nvec = (0.0, normal) if axis == "x" else (normal, 0.0)
    a = math.radians(angle_deg)
    d = (closed_dir[0] * math.cos(a) + nvec[0] * math.sin(a), closed_dir[1] * math.cos(a) + nvec[1] * math.sin(a))
    yaw = math.degrees(math.atan2(d[1], d[0]))
    hinge_xy = (h_along, face + normal * 0.025) if axis == "x" else (face + normal * 0.025, h_along)
    leaf = ctx.group(f"{path}/Leaf", translate=(hinge_xy[0], hinge_xy[1], 0.0), rotate=(0, 0, yaw))
    t = 0.04
    ctx.box(str(leaf.GetPath()), "Panel", (width - 0.01, t, height - 0.01), ((width - 0.01) / 2, 0, (height - 0.01) / 2),
            leaf_mat)
    ctx.cyl(str(leaf.GetPath()), "Handle", 0.012, 0.13, "y", (width - 0.09, 0.0, 1.0), ctx.looks.get("Metal"), collide=False)
    return {"path": path, "open_angle_deg": angle_deg, "hinge": [hinge_xy[0], hinge_xy[1]]}


def build_shell(ctx, materials):
    spec, lay = ctx.spec, ctx.spec["layout"]
    L, W = spec["footprint_m"]
    H = spec["ceiling_height_m"]
    t = ctx.cfg["room"]["wall_thickness_m"]
    wall_mat, wall_uv = materials["wall"]
    floor_mat, floor_uv = materials["floor"]
    ceil_mat, ceil_uv = materials["ceiling"]
    shell = ctx.group(f"{ctx.root}/Shell")
    sp = str(shell.GetPath())
    top = H + CEILING_T

    floor = ctx.group(f"{sp}/Floor", label="floor")
    ctx.box(str(floor.GetPath()), "FloorSlab", (L + 2 * t, W + 2 * t, FLOOR_T), (L / 2, W / 2, -FLOOR_T / 2),
            floor_mat, floor_uv)
    ceiling = ctx.group(f"{sp}/Ceiling", label="ceiling")
    ctx.box(str(ceiling.GetPath()), "CeilingSlab", (L + 2 * t, W + 2 * t, CEILING_T), (L / 2, W / 2, H + CEILING_T / 2),
            ceil_mat, ceil_uv)

    con = lay["changing_room"]["door"]                  # connecting door check-in room -> X-ray room (west wall)
    openings = {"south": [], "north": [], "west": [(con["center"][1], con["width"], con["height"])], "east": []}
    walls = ctx.group(f"{sp}/Walls", label="wall")
    wp = str(walls.GetPath())
    _wall(ctx, wp, "South", "x", -t, L + t, -t, 0.0, openings["south"], top, wall_mat, wall_uv)
    _wall(ctx, wp, "North", "x", -t, L + t, W, W + t, openings["north"], top, wall_mat, wall_uv)
    _wall(ctx, wp, "West", "y", 0.0, W, -t, 0.0, openings["west"], top, wall_mat, wall_uv)
    _wall(ctx, wp, "East", "y", 0.0, W, L, L + t, openings["east"], top, wall_mat, wall_uv)

    # entrance = outer door of the check-in room (in its wall, built by build_changing_room), swings out
    ent = lay["entrance"]
    doors = ctx.group(f"{sp}/Doors")
    along = ent["center"][1] if ent["axis"] == "y" else ent["center"][0]
    n = ent["out_normal"][0] if ent["axis"] == "y" else ent["out_normal"][1]
    face = ent["plane"][1] if n > 0 else ent["plane"][0]
    entrance = _door(ctx, str(doors.GetPath()), "Entrance", ent["axis"], along, ent["width"], ent["height"], face, n,
                     ent["hinge"], ent["open_angle_deg"], t, materials["door_leaf"], materials["door_frame"])
    return {"entrance": entrance}


def build_changing_room(ctx, materials):
    spec, lay = ctx.spec, ctx.spec["layout"]
    cr = lay["changing_room"]
    H = spec["ceiling_height_m"]
    t = ctx.cfg["room"]["wall_thickness_m"]
    wall_mat, wall_uv = materials["wall"]
    grp = ctx.group(f"{ctx.root}/CheckIn")
    gp = str(grp.GetPath())
    it, block = Rect.from_list(cr["interior"]), Rect.from_list(cr["block"])
    north = cr["corner"] == "north"

    # annex floor + ceiling (the X-ray room's west wall is the shared wall)
    floor = ctx.group(f"{gp}/Floor", label="floor")
    floor_mat, floor_uv = materials["floor"]
    ctx.box(str(floor.GetPath()), "FloorSlab", (block.sx, block.sy, FLOOR_T), (block.cx, block.cy, -FLOOR_T / 2),
            floor_mat, floor_uv)
    ceiling = ctx.group(f"{gp}/Ceiling", label="ceiling")
    ceil_mat, ceil_uv = materials["ceiling"]
    ctx.box(str(ceiling.GetPath()), "CeilingSlab", (block.sx, block.sy, CEILING_T), (block.cx, block.cy, H + CEILING_T / 2),
            ceil_mat, ceil_uv)

    # walls: west, outer (in line with the X-ray room's north / south wall) and inner; the entrance opens in one
    ent = lay["entrance"]
    on_west = ent["placed_on"] == "west"
    op_w = [(ent["center"][1], ent["width"], ent["height"])] if on_west else []
    op_o = [] if on_west else [(ent["center"][0], ent["width"], ent["height"])]
    top = H + CEILING_T
    walls = ctx.group(f"{gp}/Walls", label="wall")
    wp = str(walls.GetPath())
    _wall(ctx, wp, "West", "y", block.y0, block.y1, block.x0, it.x0, op_w, top, wall_mat, wall_uv)
    outer, inner = ((it.y1, block.y1), (block.y0, it.y0)) if north else ((block.y0, it.y0), (it.y1, block.y1))
    _wall(ctx, wp, "Outer", "x", it.x0, block.x1, outer[0], outer[1], op_o, top, wall_mat, wall_uv)
    _wall(ctx, wp, "Inner", "x", it.x0, block.x1, inner[0], inner[1], [], top, wall_mat, wall_uv)

    # connecting door in the shared west wall of the X-ray room, swings into the X-ray room
    door = cr["door"]
    info = _door(ctx, gp, "Door", "y", door["center"][1], door["width"], door["height"], door["plane"][1], 1,
                 door["hinge"], door["open_angle_deg"], t, materials["door_leaf"], materials["door_frame"])

    # bench
    b = cr["bench"]
    r = Rect.from_list(b["rect"])
    bench = ctx.group(f"{gp}/Bench", translate=(r.cx, r.cy, 0), rotate=(0, 0, b["yaw_deg"]), label="bench")
    bpath = str(bench.GetPath())
    seat = ctx.looks.color(b["color"], 0.5)
    leg = ctx.looks.get("Metal")
    lb, db, hb = b["length_m"], b["depth_m"], b["height_m"]
    ctx.box(bpath, "Seat", (lb, db, 0.04), (0, 0, hb - 0.02), seat)
    for k, x in enumerate((-lb / 2 + 0.06, lb / 2 - 0.06)):
        ctx.box(bpath, f"Support{k}", (0.04, db - 0.06, hb - 0.04), (x, 0, (hb - 0.04) / 2), leg)

    def wall_frame(item):
        x, y = (item["along"], item["coord"]) if item["axis"] == "x" else (item["coord"], item["along"])
        return x, y

    # hooks above the bench
    hk = cr["hooks"]
    hooks = ctx.group(f"{gp}/Hooks", label="coat_hook")
    for k, a in enumerate(hk["along"]):
        x, y = (a, hk["coord"]) if hk["axis"] == "x" else (hk["coord"], a)
        h = ctx.group(f"{hooks.GetPath()}/Hook_{k + 1:02d}", translate=(x, y, hk["z_m"]), rotate=(0, 0, hk["yaw_deg"]))
        ctx.box(str(h.GetPath()), "Plate", (0.05, 0.01, 0.08), (0, 0.005, 0), leg, collide=False)
        ctx.cyl(str(h.GetPath()), "Peg", 0.008, 0.07, "y", (0, 0.045, 0.01), leg, collide=False)

    # shelf with folded gowns
    sh = cr["shelf"]
    x, y = wall_frame(sh)
    shelf = ctx.group(f"{gp}/GownShelf", translate=(x, y, sh["z_m"]), rotate=(0, 0, sh["yaw_deg"]), label="shelf")
    spath = str(shelf.GetPath())
    ctx.box(spath, "Board", (sh["width_m"], sh["depth_m"], 0.025), (0, sh["depth_m"] / 2, 0), ctx.looks.color("#e8e6e0", 0.5))
    n = len(sh["gown_colors"])
    for k, color in enumerate(sh["gown_colors"]):
        gx = (k - (n - 1) / 2) * (sh["width_m"] / n)
        ctx.box(spath, f"Gown_{k + 1}", (sh["width_m"] / n - 0.03, sh["depth_m"] - 0.06, 0.07),
                (gx, sh["depth_m"] / 2, 0.0125 + 0.035), ctx.looks.color(color, 0.9), collide=False)
        ctx.label(ctx.stage.GetPrimAtPath(f"{spath}/Gown_{k + 1}"), "gown")
    if cr.get("mirror"):
        mi = cr["mirror"]
        x, y = wall_frame(mi)
        mirror = ctx.group(f"{gp}/Mirror", translate=(x, y, mi["z_m"]), rotate=(0, 0, mi["yaw_deg"]), label="mirror")
        ctx.box(str(mirror.GetPath()), "Glass", (mi["width_m"], 0.006, mi["height_m"]), (0, 0.003, mi["height_m"] / 2),
                ctx.looks.make("Mirror", color="#ffffff", roughness=0.02, metallic=1.0), collide=False)
    if cr.get("chair"):
        c = cr["chair"]
        r = Rect.from_list(c["rect"])
        size = ctx.cfg["props"]["items"]["chair"]["size_m"]
        props_mod.build_item(ctx, gp, {"kind": "chair", "name": "Chair", "color": c["color"], "yaw_deg": c["yaw_deg"],
                                       "center": [r.cx, r.cy], "size_m": size})
    return {"door": info}
