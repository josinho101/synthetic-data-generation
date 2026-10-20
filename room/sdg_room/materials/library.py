"""Room material set: procedural textures for floor / walls / ceiling / decals + UsdPreviewSurface materials."""

from . import textures


def build_room_materials(ctx) -> dict:
    """Generate this room's textures and materials. Returns {role: (material, uv meters-per-repeat)} for the
    shell plus the shared equipment materials (looked up by name via ctx.looks.get)."""
    spec, mat_cfg = ctx.spec, ctx.cfg["materials"]
    res = int(mat_cfg.get("texture_resolution", 1024))
    tdir = ctx.texture_dir
    tdir.mkdir(parents=True, exist_ok=True)
    rid = spec["id"]
    files = {}

    floor = spec["floor"]
    fname = f"{rid}_floor_{floor['material']}.png"
    if floor["material"] == "vinyl":
        floor_uv = textures.vinyl(tdir / fname, floor["color"], floor["speckle"], floor["texture_seed"], res,
                                  floor["tex_size_m"])
    elif floor["material"] == "tile":
        floor_uv = textures.tiles(tdir / fname, floor["color"], floor["grout_color"], floor["tile_size_m"],
                                  floor["texture_seed"], res)
    else:
        floor_uv = textures.concrete(tdir / fname, floor["color"], floor["texture_seed"], res, floor["tex_size_m"])
    files["floor"] = fname
    floor_mat = ctx.looks.make("Floor", texture=ctx.tex(fname), roughness=floor["roughness"])

    walls = spec["walls"]
    if walls["finish"] == "tiled":
        wname = f"{rid}_wall_tiles.png"
        wall_uv = textures.tiles(tdir / wname, walls["color"], walls["grout_color"], walls["tile_size_m"],
                                 spec["seed"] % (1 << 30), res, n=4, grout_m=0.003, variation=0.015)
        wall_mat = ctx.looks.make("Wall", texture=ctx.tex(wname), roughness=walls["roughness"], clearcoat=0.3)
        files["wall"] = wname
    else:
        wall_uv = 1.0
        wall_mat = ctx.looks.make("Wall", color=walls["color"], roughness=walls["roughness"])

    ceil = mat_cfg["ceiling"]
    cname = f"{rid}_ceiling.png"
    ceil_uv = textures.ceiling_grid(tdir / cname, ceil["color"], ceil["tbar_color"], ceil["grid_m"],
                                    spec["seed"] % (1 << 30) + 7, min(res, 512))
    files["ceiling"] = cname
    ceil_mat = ctx.looks.make("Ceiling", texture=ctx.tex(cname), roughness=ceil["roughness"])

    fin = spec["finish"]
    ctx.looks.make("EquipBody", color=fin["body_color"], roughness=fin["body_roughness"], clearcoat=fin["clearcoat"])
    ctx.looks.make("EquipAccent", color=fin["accent_color"], roughness=min(1.0, fin["body_roughness"] + 0.1),
                   clearcoat=fin["clearcoat"] * 0.5)
    ctx.looks.make("Metal", color=fin["metal_color"], roughness=fin["metal_roughness"], metallic=1.0)
    det_cfg = ctx.cfg["equipment"]["detector"]
    dname = f"{rid}_detector_front.png"
    textures.detector_front(tdir / dname, fin["detector_front_color"], det_cfg["housing_size_m"][:2],
                            det_cfg["active_area_m"], det_cfg.get("aec_chambers", 3), min(res, 1024))
    files["detector_front"] = dname
    ctx.looks.make("DetectorFront", texture=ctx.tex(dname), roughness=fin["body_roughness"], clearcoat=fin["clearcoat"])

    tape_color = spec["layout"]["marker"]["tape_color"]
    ctx.looks.make("Tape", color=tape_color, roughness=0.45)
    pname = f"{rid}_footprints.png"
    textures.footprints(tdir / pname, tape_color)
    files["footprints"] = pname
    ctx.looks.make("Footprints", texture=ctx.tex(pname), roughness=0.5, opacity_from_texture=True)

    door_cfg = mat_cfg["doors"]
    leaf = ctx.looks.make("DoorLeaf", color=spec["door_color"], roughness=door_cfg["roughness"])
    frame = ctx.looks.make("DoorFrame", color=door_cfg["frame_color"], roughness=0.35, metallic=0.6)
    return {"wall": (wall_mat, wall_uv), "floor": (floor_mat, floor_uv), "ceiling": (ceil_mat, ceil_uv),
            "door_leaf": leaf, "door_frame": frame, "files": files}
