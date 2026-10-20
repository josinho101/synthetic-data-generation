"""Optional QA renders of a room USD with Blender: three perspective views + a top view without the ceiling.

    blender -b --python scripts/blender_preview.py -- <room or scene>.usd(a) [out_prefix] [--eevee] [--cameras]
                                                     [--meta <room>.json]

Writes <prefix>_view1.png (from the entrance end), _view2.png (from the far end), _view3.png (towards the
detector) and _top.png. Default engine: Workbench (material colours, fast, geometry check). --eevee renders
with the room's own lights; Blender's light units differ from Isaac Sim RTX, so the light energy is rescaled and
the brightness is only indicative. Camera positions come from <room>.json next to the USD.
--cameras also renders through every USD camera of the room (<prefix>_cam_<name>.png).
"""

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv:
    print(__doc__)
    sys.exit(2)
eevee = "--eevee" in argv
through_cameras = "--cameras" in argv
meta_path = argv[argv.index("--meta") + 1] if "--meta" in argv else None
if meta_path:
    argv.remove("--meta")
    argv.remove(meta_path)
argv = [a for a in argv if a not in ("--eevee", "--cameras")]
usd = Path(argv[0]).resolve()
prefix = argv[1] if len(argv) > 1 else str(usd.with_suffix(""))
meta = json.loads(Path(meta_path or usd.with_suffix(".json")).read_text())   # a scene: pass the room's JSON
L, W = meta["room"]["footprint_m"]
H = meta["room"]["ceiling_height_m"]
a = meta["anchors"]
place = meta.get("placement") or {"yaw_deg": 0.0, "translate_m": [0.0, 0.0, 0.0]}


def S(p):
    """Room frame -> stage (the root prim carries the placement transform)."""
    c, s_ = math.cos(math.radians(place["yaw_deg"])), math.sin(math.radians(place["yaw_deg"]))
    t = place["translate_m"]
    return (p[0] * c - p[1] * s_ + t[0], p[0] * s_ + p[1] * c + t[1], p[2])


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.usd_import(filepath=str(usd))
scene = bpy.context.scene
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
if eevee:
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE") if e in engines)
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and obj.data.type == "AREA":
            obj.data.energy = 60.0 * obj.data.size * getattr(obj.data, "size_y", obj.data.size)
    scene.view_settings.view_transform = "AgX" if "AgX" in [v.identifier for v in
        type(scene.view_settings).bl_rna.properties["view_transform"].enum_items] else "Filmic"
else:
    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light, shading.color_type = "STUDIO", "MATERIAL"
    shading.show_shadows, shading.show_cavity = True, True
    shading.cavity_type = "BOTH"
world = bpy.data.worlds.new("preview")
scene.world = world

cam_data = bpy.data.cameras.new("preview_cam")
cam = bpy.data.objects.new("preview_cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def shoot(eye, target, lens, name):
    eye, target = S(eye), S(target)
    cam.location = Vector(eye)
    cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
    cam_data.lens = lens
    scene.render.filepath = f"{prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)


x_open = max(0.0, meta["changing_room"]["block"][2]) + 0.15     # just inside the X-ray room (check-in room: x < 0)
det, focal = a["detector_center"], a["focal_spot"]
shoot((x_open, W / 2, H - 0.25), (L, W / 2, 0.9), 13, "view1")
shoot((L - 0.15, W / 2, H - 0.25), (0.0, W / 2, 0.9), 13, "view2")
side = 1 if focal[1] > det[1] else -1
eye_x = det[0] - 1.6 if det[0] - 1.6 > x_open else min(L - 0.2, det[0] + 1.6)
shoot((eye_x, focal[1] - side * 0.3, H - 0.3), (det[0], det[1], det[2] - 0.4), 16, "view3")
for obj in bpy.data.objects:   # top view: hide the ceiling slab and everything mounted on it
    if obj.type == "MESH":
        z_min = min((obj.matrix_world @ Vector(c)).z for c in obj.bound_box)
        if z_min > H - 0.1:
            obj.hide_render = True
cam_data.type = "ORTHO"
cam_data.ortho_scale = max(L, W) + 0.6
if round(place["yaw_deg"] / 90.0) % 2:     # room length runs along stage Y: portrait image
    scene.render.resolution_x, scene.render.resolution_y = 720, 1280
cam.location, cam.rotation_euler = Vector(S((L / 2, W / 2, 10.0))), (0.0, 0.0, 0.0)
scene.render.filepath = f"{prefix}_top.png"
bpy.ops.render.render(write_still=True)

if through_cameras:
    for obj in bpy.data.objects:
        obj.hide_render = False
    for cinfo in meta.get("cameras", []):
        obj = bpy.data.objects.get(cinfo["name"])
        if obj is None or obj.type != "CAMERA":
            print(f"camera {cinfo['name']} not imported")
            continue
        scene.camera = obj
        scene.render.resolution_x, scene.render.resolution_y = cinfo["resolution"]
        scene.render.filepath = f"{prefix}_cam_{cinfo['name']}.png"
        bpy.ops.render.render(write_still=True)
