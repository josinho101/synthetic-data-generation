"""Build one room: spec + layout (from the manifest) -> <id>.usd + textures/ (pure Python, usd-core)."""

import logging
from pathlib import Path

from pxr import Gf, UsdGeom

from ..materials.library import build_room_materials
from ..photometry import room_lighting
from ..placement import Placement, entrance_outward
from .cameras import build_cameras
from .context import BuildContext
from .equipment import build_floor_marker, build_tube_stand, build_wall_stand
from .lighting import build_lights
from .props import build_props
from .shell import build_changing_room, build_shell
from .stage import create_stage, set_custom

_LOG = logging.getLogger("sdg_room.usd.build")


def build_room_usd(cfg: dict, spec: dict, room_dir: Path, generator_version: str) -> dict:
    """Write <room_dir>/<id>.<ext>; returns paths of the key prims, photometry and the texture list."""
    room_dir = Path(room_dir)
    room_dir.mkdir(parents=True, exist_ok=True)
    usd_cfg = cfg["export"]["usd"]
    ext = usd_cfg.get("file_format", "usd")
    usd_path = room_dir / f"{spec['id']}.{ext}"
    if usd_path.exists():
        usd_path.unlink()
    root_path = usd_cfg.get("root_prim", "/Room")
    stage, root = create_stage(usd_path, root_path, usd_cfg.get("meters_per_unit", 1.0), usd_cfg.get("up_axis", "Z"))
    for key, value in (("room_id", spec["id"]), ("seed", float(spec["seed"])), ("generator_version", generator_version),
                       ("footprint_m", [spec["footprint_m"][0], spec["footprint_m"][1], spec["ceiling_height_m"]])):
        set_custom(root, key, value)
    stage.SetMetadata("comment", f"Synthetic X-ray room {spec['id']} (sdg_room {generator_version})")
    place = Placement(spec, cfg)
    _place_root(stage, root, spec, cfg, place)

    ctx = BuildContext(stage, root_path, cfg, spec, room_dir / "textures")
    materials = build_room_materials(ctx)
    _LOG.info(f"{spec['id']}: textures {sorted(materials['files'].values())}")

    prims = {}
    prims["shell"] = build_shell(ctx, materials)
    prims["checkin"] = build_changing_room(ctx, materials)
    ctx.group(f"{root_path}/Equipment")
    prims["wall_stand"] = build_wall_stand(ctx)
    prims["tube_stand"] = build_tube_stand(ctx)
    prims["markers"] = build_floor_marker(ctx)
    prims["props"] = build_props(ctx)
    photometry = room_lighting(spec, cfg)
    prims["lights"] = build_lights(ctx, photometry)
    prims["cameras"] = build_cameras(ctx)
    _LOG.info(f"{spec['id']}: exam panels {photometry['exam']['luminance_nits']:.0f} nits -> estimated "
              f"{photometry['exam']['estimated_lux_mean']:.0f} lux (target {spec['lux_target']:.0f}), "
              f"uniformity {photometry['exam']['uniformity_min_over_mean']:.2f}")
    stage.GetRootLayer().Save()
    return {"usd": str(usd_path), "prims": prims, "photometry": photometry, "textures": materials["files"],
            "semantic_labels": ctx.labels, "placement": place.as_dict()}


def _place_root(stage, root, spec, cfg, place: Placement) -> None:
    """Root transform (door faces the viewer) + Isaac viewport start camera in front of the door."""
    xf = UsdGeom.Xformable(root)
    xf.AddTranslateOp().Set(Gf.Vec3d(*place.translate))
    xf.AddRotateZOp().Set(float(place.yaw_deg))
    set_custom(root, "door_facing", place.door_facing)
    out = entrance_outward(spec)
    set_custom(root, "entrance_outward_room", [out[0], out[1], 0.0])
    set_custom(root, "placement_origin", place.origin_mode)
    pcfg = cfg["export"].get("placement") or {}
    if pcfg.get("set_viewport_camera", True):
        door = spec["layout"]["entrance"]["center"]
        d = float(pcfg.get("viewer_distance_m", 6.0))
        eye = place.to_stage([door[0] + out[0] * d, door[1] + out[1] * d, float(pcfg.get("viewer_height_m", 2.0))])
        target = place.to_stage([door[0], door[1], 1.0])
        stage.GetRootLayer().customLayerData = {"cameraSettings": {
            "boundCamera": "/OmniverseKit_Persp",
            "Perspective": {"position": Gf.Vec3d(*eye), "target": Gf.Vec3d(*target)}}}
