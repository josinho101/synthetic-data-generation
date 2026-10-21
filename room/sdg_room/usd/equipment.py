"""X-ray equipment: wall stand + flat-panel detector + patient grips, floor-rail tube stand, floor marker.

Wall stand frame: origin on the detector wall at the stand centre, +Y into the room.
Tube stand frame: origin on the tube wall at the rail centre, +Y towards the detector.
Moving parts are separate Xforms so Isaac Sim scripts can drive them:
  WallStand/Carriage          translate Z  = detector centre height  (sdg:travel_min / sdg:travel_max)
  TubeStand/Carriage          translate X  = position along the rail (sdg:travel_min / sdg:travel_max)
  TubeStand/Carriage/Arm      translate Z  = tube centre height
  .../Arm/TubeHead            at the focal spot; its +Y is the beam direction (rotate it to angle the tube)
"""

from ..layout.solver import collimator_front
from .fov_light import build_fov_light
from .stage import set_custom


def build_wall_stand(ctx):
    eq, lay = ctx.cfg["equipment"], ctx.spec["layout"]["equipment"]
    ws_cfg, det, hd = eq["wall_stand"], eq["detector"], eq["handles"]
    ws = lay["wall_stand"]
    body, accent, metal = ctx.looks.get("EquipBody"), ctx.looks.get("EquipAccent"), ctx.looks.get("Metal")
    grp = ctx.group(f"{ctx.root}/Equipment/WallStand", translate=(ws["origin"][0], ws["origin"][1], 0),
                    rotate=(0, 0, ws["yaw_deg"]), label="wall_stand")
    p = str(grp.GetPath())
    if ctx.reference_asset(p, ws_cfg.get("asset")):
        return {"path": p, "asset": ws_cfg["asset"]}
    bw, bd, bh = ws_cfg["base_size_m"]
    cw, cd = ws_cfg["column_size_m"]
    gap = ws_cfg["wall_gap_m"]
    col_h = min(ws["column_height_m"], ctx.spec["ceiling_height_m"] - 0.10)   # stays below a low ceiling
    hw, hh, hdp = det["housing_size_m"]
    ctx.box(p, "Base", (bw, bd, bh), (0, bd / 2, bh / 2), accent)
    ctx.box(p, "Column", (cw, cd, col_h), (0, gap + cd / 2, col_h / 2), body)
    ctx.box(p, "ColumnTrim", (cw * 0.35, 0.004, col_h - 0.1), (0, gap + cd + 0.002, col_h / 2), accent, collide=False)
    ctx.box(p, "TopCap", (cw + 0.02, cd + 0.02, 0.04), (0, gap + cd / 2, col_h + 0.02), accent)

    carriage = ctx.group(f"{p}/Carriage", translate=(0, 0, ws["detector_center_height_m"]))
    cp = carriage.GetPrim()
    set_custom(cp, "travel_axis", "z")
    set_custom(cp, "travel_min", ws_cfg["carriage_travel_m"][0])
    set_custom(cp, "travel_max", ws_cfg["carriage_travel_m"][1])
    c = str(carriage.GetPath())
    ctx.box(c, "Sleeve", (cw + 0.04, cd + 0.02, 0.30), (0, gap + cd / 2, 0), accent)
    detector = ctx.group(f"{c}/Detector", label="wall_detector")
    d = str(detector.GetPath())
    y_mid = gap + cd + hdp / 2
    ctx.box(d, "Housing", (hw, hdp, hh), (0, y_mid, 0), body)
    front = ctx.box(d, "ActiveArea", (hw - 0.02, 0.002, hh - 0.02), (0, gap + cd + hdp + 0.001, 0),
                    ctx.looks.get("DetectorFront"), uv="fit", collide=False)
    ctx.label(front.GetPrim(), "detector_active_area")

    handles = ctx.group(f"{d}/Handles", label="detector_handle")
    hp = str(handles.GetPath())
    r, length, so = hd["bar_radius_m"], hd["side_length_m"], hd["standoff_m"]
    if hd.get("side", True):
        for side, sgn in (("L", -1), ("R", 1)):
            x_bar = sgn * (hw / 2 + so + r)
            ctx.cyl(hp, f"Handle_{side}", r, length, "z", (x_bar, y_mid, 0), metal)
            for k, z in enumerate((-length / 2 + 0.03, length / 2 - 0.03)):
                ctx.cyl(hp, f"Standoff_{side}{k}", r * 0.7, so + r, "x", (sgn * (hw / 2 + (so + r) / 2), y_mid, z), metal)
    if ws.get("top_bar"):
        z_bar = hh / 2 + so + r
        ctx.cyl(hp, "Handle_Top", r, hw * 0.8, "x", (0, y_mid, z_bar), metal)
        for k, x in enumerate((-hw * 0.35, hw * 0.35)):
            ctx.cyl(hp, f"Standoff_T{k}", r * 0.7, so + r, "z", (x, y_mid, hh / 2 + (so + r) / 2), metal)
    return {"path": p, "carriage": c, "detector": d, "active_area": str(front.GetPath()), "handles": hp}


def build_tube_stand(ctx):
    eq, lay = ctx.cfg["equipment"], ctx.spec["layout"]["equipment"]
    t_cfg, ts = eq["tube_stand"], lay["tube_stand"]
    H = ctx.spec["ceiling_height_m"]
    body, accent, metal = ctx.looks.get("EquipBody"), ctx.looks.get("EquipAccent"), ctx.looks.get("Metal")
    grp = ctx.group(f"{ctx.root}/Equipment/TubeStand", translate=(ts["origin"][0], ts["origin"][1], 0),
                    rotate=(0, 0, ts["yaw_deg"]), label="xray_tube_stand")
    p = str(grp.GetPath())
    if ctx.reference_asset(p, t_cfg.get("asset")):
        return {"path": p, "asset": t_cfg["asset"]}
    rail_len, (rw, rh) = ts["rail_length_m"], t_cfg["rail_size_m"]
    ro = t_cfg["rail_offset_m"]
    rail = ctx.group(f"{p}/Rail", label="tube_rail")
    rp = str(rail.GetPath())
    ctx.box(rp, "Track", (rail_len, rw, rh), (0, ro, rh / 2), metal)
    for k, x in enumerate((-rail_len / 2 + 0.03, rail_len / 2 - 0.03)):
        ctx.box(rp, f"EndStop{k}", (0.06, rw + 0.04, rh + 0.04), (x, ro, (rh + 0.04) / 2), accent)

    cwid, cdep, chgt = t_cfg["carriage_size_m"]
    colw, cold = t_cfg["column_size_m"]
    floor_ceiling = ts["column_type"] == "floor_ceiling"
    col_base = rh + chgt
    col_h = (H - 0.08 - col_base) if floor_ceiling else min(ts["column_height_m"], H - 0.10 - col_base)
    if floor_ceiling:
        ceil = ctx.group(f"{p}/CeilingRail", label="tube_rail")
        ctx.box(str(ceil.GetPath()), "Track", (rail_len, rw, 0.06), (0, ro, H - 0.03), metal)

    carriage = ctx.group(f"{p}/Carriage", translate=(ts["carriage_x_m"], 0, 0))
    cp = carriage.GetPrim()
    set_custom(cp, "travel_axis", "x")
    set_custom(cp, "travel_min", -rail_len / 2 + 0.25)
    set_custom(cp, "travel_max", rail_len / 2 - 0.25)
    c = str(carriage.GetPath())
    ctx.box(c, "Base", (cwid, cdep, chgt), (0, ro, rh + chgt / 2), accent)
    ctx.box(c, "Column", (colw, cold, col_h), (0, ro, col_base + col_h / 2), body)
    if floor_ceiling:
        ctx.box(c, "TopGuide", (colw + 0.06, cold + 0.04, 0.02), (0, ro, col_base + col_h + 0.01), accent)

    det_h = ctx.spec["layout"]["equipment"]["detector"]["center"][2]
    arm = ctx.group(f"{c}/Arm", translate=(0, 0, det_h))
    ap = arm.GetPrim()
    set_custom(ap, "travel_axis", "z")
    set_custom(ap, "travel_min", col_base + 0.35)
    set_custom(ap, "travel_max", col_base + col_h - 0.2)
    a = str(arm.GetPath())
    aw, ah = t_cfg["arm_size_m"]
    ctx.box(a, "Sleeve", (colw + 0.05, cold + 0.05, 0.28), (0, ro, 0), accent)
    arm_len = ts["arm_length_m"]
    ctx.box(a, "Beam", (aw, arm_len, ah), (0, ro + cold / 2 + arm_len / 2, 0), body)

    head = ctx.group(f"{a}/TubeHead", translate=(0, ts["focal_offset_m"], 0), label="xray_tube")
    hp = head.GetPrim()
    set_custom(hp, "beam_axis_local", [0.0, 1.0, 0.0])
    h = str(head.GetPath())
    hr, hl = t_cfg["housing_radius_m"], t_cfg["housing_length_m"]
    ctx.cyl(h, "Housing", hr, hl, "x", (0, 0, 0), body)
    for k, x in enumerate((-hl / 2 - 0.015, hl / 2 + 0.015)):
        ctx.cyl(h, f"EndCap{k}", hr * 0.9, 0.03, "x", (x, 0, 0), accent)
    cw2, cd2, ch2 = t_cfg["collimator_size_m"]
    c_front = collimator_front(t_cfg)
    collimator = ctx.group(f"{h}/Collimator", label="collimator")
    cpath = str(collimator.GetPath())
    ctx.box(cpath, "Body", (cw2, cd2, ch2), (0, c_front - cd2 / 2, 0), accent)
    ctx.box(cpath, "LightWindow", (cw2 * 0.55, 0.004, ch2 * 0.55), (0, c_front + 0.002, 0),
            ctx.looks.make("CollimatorGlass", color="#cfe3e8", roughness=0.05, opacity=0.5), collide=False)
    ctx.box(cpath, "Knobs", (cw2 * 0.8, 0.03, 0.03), (0, c_front - cd2 / 2, ch2 / 2 + 0.015), body, collide=False)
    ctx.cyl(cpath, "Handle", 0.014, cw2 + 0.06, "x", (0, c_front - 0.03, -ch2 / 2 - 0.035), metal)
    for k, x in enumerate((-cw2 / 2 - 0.01, cw2 / 2 + 0.01)):
        ctx.cyl(cpath, f"HandlePost{k}", 0.008, 0.035, "z", (x, c_front - 0.03, -ch2 / 2 - 0.0175), metal, collide=False)
    fov = build_fov_light(ctx, cpath, c_front, float(ctx.spec["layout"]["equipment"]["sid_m"]))
    focal = ctx.group(f"{h}/FocalSpot")
    set_custom(focal.GetPrim(), "sid_m", ctx.spec["layout"]["equipment"]["sid_m"])
    return {"path": p, "carriage": c, "arm": a, "tube_head": h, "collimator": cpath, "focal_spot": str(focal.GetPath()),
            "fov_light": fov,
            "rail": rp}


def _tape_outline(ctx, frame_path, tape, center_line=False):
    """Tape rectangle (+ optional centre line behind it) and footprint decal in a marker frame (toes local -Y)."""
    mk_cfg = ctx.cfg["equipment"]["floor_marker"]
    tw, z = mk_cfg["tape_width_m"], 0.0008
    ow, od = mk_cfg["outline_size_m"]
    for name, size, center in (("OutlineFront", (ow, tw, 0.0016), (0, -od / 2 + tw / 2, z)),
                               ("OutlineBack", (ow, tw, 0.0016), (0, od / 2 - tw / 2, z)),
                               ("OutlineLeft", (tw, od, 0.0016), (-ow / 2 + tw / 2, 0, z)),
                               ("OutlineRight", (tw, od, 0.0016), (ow / 2 - tw / 2, 0, z))):
        ctx.box(frame_path, name, size, center, tape, collide=False)
    if center_line:
        cl = mk_cfg["center_line_length_m"]
        ctx.box(frame_path, "CenterLine", (0.02, cl, 0.0016), (0, od / 2 + cl / 2 + 0.03, z), tape, collide=False)
    ctx.box(frame_path, "Footprints", (0.50, 0.40, 0.0012), (0, 0, 0.0018), ctx.looks.get("Footprints"), uv="fit",
            collide=False)


def build_floor_marker(ctx):
    """Patient floor marker (tape outline + centre line + footprints) with the PatientStand anchor (humans face its
    local -Y), plus the entrance marker just inside the entrance door with the EntranceStand anchor."""
    lay = ctx.spec["layout"]
    mk = lay["marker"]
    sx, sy = mk["stand_point"]
    grp = ctx.group(f"{ctx.root}/Markers", label="floor_marker")
    g = str(grp.GetPath())
    det = lay["equipment"]["detector"]
    tape = ctx.looks.get("Tape")
    # marker frame: origin at the stand point, local +Y away from the detector wall (same yaw as the wall stand)
    frame = ctx.group(f"{g}/Frame", translate=(sx, sy, 0), rotate=(0, 0, mk["yaw_deg"]))
    _tape_outline(ctx, str(frame.GetPath()), tape, center_line=True)
    stand = ctx.group(f"{g}/PatientStand", translate=(sx, sy, 0), rotate=(0, 0, mk["yaw_deg"]))
    sp = stand.GetPrim()
    set_custom(sp, "faces", "-Y towards the detector (synthetic humans face -Y)")
    set_custom(sp, "detector_center", det["center"])
    out = {"path": g, "patient_stand": str(stand.GetPath()), "entrance_stand": None}
    em = lay.get("entrance_marker")
    if em:
        ex, ey = em["stand_point"]
        eframe = ctx.group(f"{g}/EntranceFrame", translate=(ex, ey, 0), rotate=(0, 0, em["yaw_deg"]))
        _tape_outline(ctx, str(eframe.GetPath()), tape)
        estand = ctx.group(f"{g}/EntranceStand", translate=(ex, ey, 0), rotate=(0, 0, em["yaw_deg"]))
        set_custom(estand.GetPrim(), "faces", "-Y into the room, away from the entrance door")
        out["entrance_stand"] = str(estand.GetPath())
    return out
