"""Room spec sampling: every random choice of one room (finishes, lighting, equipment settings, props).

Positions are solved afterwards by `layout.solver.solve_layout`; a layout that cannot be solved makes
the manifest resample the spec with the next attempt number (new, but still reproducible, sub-seed).
"""

from ..config.schema import ceiling_range_m, detector_face_offset, footprint_m, max_sid
from .distributions import delta_e, int_range, jitter_color, separate_color, truncated_normal, uniform, weighted_choice


def _r(value, nd=4):
    return round(float(value), nd)


def _sample_walls(rng, mat, finish):
    spec = mat["walls"][finish]
    out = {"finish": finish, "color": jitter_color(rng, rng.choice(spec["colors"]), mat.get("color_jitter", {})),
           "roughness": _r(uniform(rng, spec["roughness"]), 3)}
    if spec.get("tile_size_m"):
        out["tile_size_m"] = rng.choice(spec["tile_size_m"])
        out["grout_color"] = rng.choice(spec["grout_colors"])
    return out


def _sample_floor(rng, mat, kind):
    spec = mat["floors"][kind]
    out = {"material": kind, "color": jitter_color(rng, rng.choice(spec["colors"]), mat.get("color_jitter", {})),
           "roughness": _r(uniform(rng, spec["roughness"]), 3), "texture_seed": rng.randrange(1 << 30)}
    if kind == "vinyl":
        out["speckle"] = _r(uniform(rng, spec["speckle"]), 3)
        out["tex_size_m"] = spec["tex_size_m"]
    elif kind == "tile":
        out["tile_size_m"] = rng.choice(spec["tile_size_m"])
        out["grout_color"] = rng.choice(spec["grout_colors"])
    else:
        out["tex_size_m"] = spec["tex_size_m"]
    return out


def _sample_equipment_finish(rng, mat):
    eq, glare = mat["equipment"], mat["glare_levels"][mat["glare"]]
    return {"glare": mat["glare"], "body_color": rng.choice(eq["body_colors"]),
            "accent_color": rng.choice(eq["accent_colors"]),
            "body_roughness": _r(uniform(rng, glare["roughness"]), 3),
            "clearcoat": _r(uniform(rng, glare["clearcoat"]), 3),
            "metal_roughness": _r(uniform(rng, eq["metal_roughness"]), 3),
            "metal_color": eq["metal_color"], "detector_front_color": eq["detector_front_color"]}


def _sample_props(rng, props_cfg):
    """Which optional items are requested (the layout solver may still drop items that do not fit)."""
    wanted = []
    for name, item in props_cfg["items"].items():
        if name == "cable_runs":
            continue
        count = int_range(rng, item["count"]) if "count" in item else int(rng.random() < item.get("p", 1.0))
        for i in range(count):
            entry = {"kind": name, "name": f"{name}_{i + 1:02d}", "color": rng.choice(item["colors"])}
            if name == "apron_rack":
                entry["aprons"] = [rng.choice(item["colors"]) for _ in range(int_range(rng, item["aprons"]))]
            wanted.append(entry)
    cables = props_cfg["items"].get("cable_runs")
    cable_runs = {"count": int_range(rng, cables["count"]), "color": rng.choice(cables["colors"])} if cables else None
    return wanted, cable_runs


def sample_spec(cfg: dict, index: int, room_id: str, rng, attempt: int, room_seed: int) -> dict:
    var, room, eq, mat, light, props = (cfg[k] for k in ("variations", "room", "equipment", "materials",
                                                         "lighting", "props"))
    length, width = footprint_m(room)
    cr = room["changing_room"]
    ws, tube, marker = eq["wall_stand"], eq["tube_stand"], eq["floor_marker"]

    sid_hi = min(tube["sid_m"][1], max_sid(eq, width))
    cct_class = weighted_choice(rng, var["cct_class"])
    panel_size = weighted_choice(rng, light["panels"]["size_weights"])
    lux = light["lux"]
    support = weighted_choice(rng, var["patient_support"])
    wanted_props, cable_runs = _sample_props(rng, props)

    spec = {
        "id": room_id, "index": index, "seed": room_seed, "attempt": attempt,
        "footprint_m": [_r(length), _r(width)],
        "ceiling_height_m": _r(uniform(rng, ceiling_range_m(room)), 3),
        "wall_finish": weighted_choice(rng, var["wall_finish"]),
        "floor_material": weighted_choice(rng, var["floor_material"]),
        "detector_side": weighted_choice(rng, var["detector_side"]),
        "changing_room_corner": weighted_choice(rng, var["changing_room_corner"]),
        "entrance_wall": weighted_choice(rng, var["entrance_wall"]),
        "changing_door_wall": weighted_choice(rng, var["changing_door_wall"]),
        "patient_support": support,
        "tube_column_type": weighted_choice(rng, var["tube_column_type"]),
        "cct_class": cct_class,
        "cct_k": _r(uniform(rng, light["cct_k"][cct_class]), 0),
        "lux_target": _r(truncated_normal(rng, lux["mean"], lux["sd"], lux["min"], lux["max"]), 1),
        "changing_lux_target": _r(uniform(rng, light["panels"]["changing_lux"]), 1),
        "panel_size": panel_size,
        "panel_count": int_range(rng, light["panels"]["count_exam"]),
        "entrance": {"width_m": _r(uniform(rng, room["entrance"]["width_m"]), 3),
                     "open_angle_deg": _r(uniform(rng, room["entrance"]["open_angle_deg"]), 1),
                     "hinge": rng.choice(["lo", "hi"]), "u": rng.random()},
        "changing_room": {"length_m": _r(uniform(rng, cr["length_m"]), 3),
                          "depth_m": _r(uniform(rng, cr["depth_m"]), 3),
                          "door_width_m": _r(uniform(rng, cr["door_width_m"]), 3),
                          "door_open_angle_deg": _r(uniform(rng, cr["door_open_angle_deg"]), 1),
                          "hinge": rng.choice(["lo", "hi"]), "u": rng.random(),
                          "mirror": rng.random() < cr["p_mirror"], "chair": rng.random() < cr["p_chair"],
                          "hooks": int_range(rng, props["changing_room"]["hook_count"]),
                          "gown_colors": [rng.choice(props["changing_room"]["gown_colors"]) for _ in range(3)],
                          "bench_color": rng.choice(props["changing_room"]["bench_colors"])},
        "equipment": {
            "detector_center_height_m": _r(uniform(rng, ws["detector_center_height_m"]), 3),
            "wall_stand_column_height_m": _r(uniform(rng, ws["column_height_m"]), 3),
            "detector_x_u": rng.random(),
            "top_bar": rng.random() < eq["handles"]["p_top_bar"],
            "sid_m": _r(uniform(rng, [tube["sid_m"][0], sid_hi]), 3),
            "rail_length_m": _r(uniform(rng, tube["rail_length_m"]), 3),
            "rail_shift_u": rng.random(),
            "tube_column_height_m": _r(uniform(rng, tube["column_height_m"]), 3),
            "stand_gap_m": _r(uniform(rng, marker["stand_gap_m"]), 3),
            "tape_color": rng.choice(marker["tape_colors"]),
            "detector_face_offset_m": _r(detector_face_offset(eq)),
        },
        "walls": None, "floor": None,
        "door_color": rng.choice(mat["doors"]["colors"]),
        "finish": _sample_equipment_finish(rng, mat),
        "props_requested": wanted_props,
        "cable_runs": cable_runs,
        "support_color": None, "support_pad_color": None,
    }
    spec["walls"] = _sample_walls(rng, mat, spec["wall_finish"])
    spec["floor"] = _sample_floor(rng, mat, spec["floor_material"])
    min_de = float(mat.get("min_floor_wall_delta_e", 0.0))
    sampled = spec["floor"]["color"]
    spec["floor"]["color"] = separate_color(sampled, spec["walls"]["color"], min_de)
    if spec["floor"]["color"] != sampled:
        spec["floor"]["color_sampled"] = sampled          # before the floor / wall contrast correction
    spec["floor"]["delta_e_to_wall"] = round(delta_e(spec["floor"]["color"], spec["walls"]["color"]), 2)
    tape = spec["equipment"]["tape_color"]
    spec["equipment"]["tape_color"] = separate_color(tape, spec["floor"]["color"], float(marker.get("min_floor_delta_e", 0.0)))
    if spec["equipment"]["tape_color"] != tape:
        spec["equipment"]["tape_color_sampled"] = tape    # before the tape / floor contrast correction
    if support != "none":
        sup = props["patient_support"][support]
        spec["support_color"] = rng.choice(sup["colors"])
        spec["support_pad_color"] = rng.choice(sup["pad_colors"])
    return spec
