"""Preview PNG: orthographic front + left-side renders placed next to each other."""

import logging
import math
import os
import tempfile
from pathlib import Path

import bpy
from mathutils import Vector

from . import colors

_LOG = logging.getLogger("sdg_humans.blender.preview")


def _pick_engine(candidates) -> str:
    available = {item.identifier for item in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items}
    for engine in candidates:
        if engine in available:
            return engine
    return "BLENDER_WORKBENCH"


def _setup_world(background_hex: str) -> None:
    world = bpy.context.scene.world or bpy.data.worlds.new("preview_world")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = colors.hex_to_linear_rgba(background_hex)
        bg.inputs["Strength"].default_value = 0.6


def _add_lights() -> list:
    created = []
    for name, rotation, energy in (("key", (50, 0, -30), 3.5), ("fill", (60, 0, 140), 1.5)):
        light = bpy.data.lights.new(f"preview_{name}", "SUN")
        light.energy = energy
        obj = bpy.data.objects.new(f"preview_{name}", light)
        obj.rotation_euler = [math.radians(a) for a in rotation]
        bpy.context.scene.collection.objects.link(obj)
        created.append(obj)
    return created


def _camera(height_m: float, view: str):
    cam_data = bpy.data.cameras.new(f"preview_{view}")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = height_m * 1.12
    cam = bpy.data.objects.new(f"preview_{view}", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    centre_z = height_m / 2.0
    if view == "front":
        cam.location = Vector((0.0, -6.0, centre_z))
        cam.rotation_euler = (math.radians(90), 0.0, 0.0)
    else:  # the human's left side faces +X
        cam.location = Vector((6.0, 0.0, centre_z))
        cam.rotation_euler = (math.radians(90), 0.0, math.radians(90))
    return cam


_DOT_COLORS = {"internal": (1.0, 0.1, 0.1), "surface": (1.0, 0.85, 0.0), "anchor": (0.0, 0.8, 1.0)}


def _overlay(tile, points: dict, height_m: float, view: str, ppm: float):
    """Draw landmark dots onto one orthographic tile (numpy array, bottom-up rows)."""
    out = tile.copy()
    rows, cols = out.shape[:2]
    for info in points.values():
        x, y, z = info["rest_position_m"]
        u = cols / 2.0 + (x if view == "front" else y) * ppm
        v = rows / 2.0 + (z - height_m / 2.0) * ppm
        r, c = int(round(v)), int(round(u))
        color = _DOT_COLORS.get(info.get("kind"), (1.0, 0.0, 1.0))
        out[max(0, r - 2):r + 3, max(0, c - 2):c + 3, :3] = color
    return out


def _save(pixels, path: Path) -> None:
    out = bpy.data.images.new(Path(path).stem, width=pixels.shape[1], height=pixels.shape[0], alpha=True)
    out.pixels[:] = pixels.ravel()
    out.filepath_raw = str(path)
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)


def render_preview(path: Path, height_m: float, preview_cfg: dict, landmarks: dict = None) -> Path:
    import numpy as np

    scene = bpy.context.scene
    engine = _pick_engine(preview_cfg.get("engines", []))
    scene.render.engine = engine
    width, height = preview_cfg.get("resolution", [512, 768])
    scene.render.resolution_x, scene.render.resolution_y = int(width), int(height)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if engine == "BLENDER_WORKBENCH":
        scene.display.shading.color_type = "MATERIAL"
    elif hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = int(preview_cfg.get("samples", 16))
    _setup_world(preview_cfg.get("background_rgb", "#d9dde3"))
    temp = _add_lights()

    tiles = []
    for view in ("front", "left"):
        cam = _camera(height_m, view)
        temp.append(cam)
        scene.camera = cam
        handle, tmp = tempfile.mkstemp(suffix=".png")
        os.close(handle)
        scene.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(tmp)
        tiles.append(np.array(img.pixels[:], dtype=np.float32).reshape(int(height), int(width), 4))
        bpy.data.images.remove(img)
        os.remove(tmp)

    _save(np.concatenate(tiles, axis=1), path)
    if landmarks and preview_cfg.get("landmark_overlay", False):
        ppm = max(int(width), int(height)) / (height_m * 1.12)
        dotted = [_overlay(t, landmarks, height_m, v, ppm) for t, v in zip(tiles, ("front", "left"))]
        _save(np.concatenate(dotted, axis=1), Path(path).with_name(Path(path).stem + "_landmarks.png"))
    for obj in temp:
        bpy.data.objects.remove(obj, do_unlink=True)
    _LOG.info(f"preview rendered with {engine} -> {Path(path).name}")
    return Path(path)
