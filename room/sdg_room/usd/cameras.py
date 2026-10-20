"""Cameras: UsdGeom.Camera prims (look-at transform, optics) + optional wall housing / bracket meshes.
RGB-D exam cameras (entries with `rig`) become an Xform <name> with one UsdGeom.Camera per stream (Color, Depth)
plus the camera body and its stand (tripod / bracket / post + arm) under <name>_Mount."""

import math

from pxr import Gf, Sdf, UsdGeom

from .stage import safe_name, set_custom


def look_at_matrix(eye, target, up=(0.0, 0.0, 1.0)) -> Gf.Matrix4d:
    """Camera-to-parent transform: the camera looks along its local -Z at `target`, +Y as close to `up` as possible."""
    eye, target = Gf.Vec3d(*eye), Gf.Vec3d(*target)
    fwd = (target - eye).GetNormalized()
    upv = Gf.Vec3d(*up)
    if abs(Gf.Dot(fwd, upv)) > 0.999:          # looking straight up/down: pick another up vector
        upv = Gf.Vec3d(0, 1, 0)
    return Gf.Matrix4d().SetLookAt(eye, target, upv).GetInverse()


def build_cameras(ctx) -> dict:
    cams = ctx.spec.get("cameras") or []
    if not cams:
        return {}
    grp = ctx.group(f"{ctx.root}/Cameras")
    gp = str(grp.GetPath())
    housing_mat = ctx.looks.color("#e9eaec", 0.35, clearcoat=0.4)
    dark = ctx.looks.color("#1d2226", 0.2)
    paths = {}
    for cam in cams:
        name = safe_name(cam["name"])
        if cam.get("rig"):
            paths[cam["name"]] = _build_rig(ctx, gp, name, cam, dark)
            continue
        camera = UsdGeom.Camera.Define(ctx.stage, f"{gp}/{name}")
        camera.AddTransformOp().Set(look_at_matrix(cam["position"], cam["target"]))
        camera.CreateProjectionAttr().Set(UsdGeom.Tokens.perspective)
        camera.CreateFocalLengthAttr().Set(float(cam["focal_length_mm"]))
        camera.CreateHorizontalApertureAttr().Set(float(cam["horizontal_aperture_mm"]))
        camera.CreateVerticalApertureAttr().Set(float(cam["vertical_aperture_mm"]))
        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(*[float(v) for v in cam["clipping_range_m"]]))
        prim = camera.GetPrim()
        prim.CreateAttribute("sdg:resolution", Sdf.ValueTypeNames.Int2, custom=True).Set(Gf.Vec2i(*cam["resolution"]))
        set_custom(prim, "target", [float(v) for v in cam["target"]])
        set_custom(prim, "mount", cam["mount"])
        set_custom(prim, "fov_h_deg", float(cam["fov_h_deg"]))
        paths[cam["name"]] = str(prim.GetPath())
        if cam.get("housing"):
            _housing(ctx, gp, name, cam, housing_mat, dark)
    return paths


def _housing(ctx, parent, name, cam, body, dark):
    """Housing behind the lens (aligned with the view) + an arm to the ceiling, in the room frame."""
    x, y, z = cam["position"]
    tx, ty, tz = cam["target"]
    yaw = math.degrees(math.atan2(ty - y, tx - x))
    pitch = math.degrees(math.atan2(tz - z, math.hypot(tx - x, ty - y)))
    mount = ctx.group(f"{parent}/{name}_Housing", translate=(x, y, z), label="security_camera")
    head = ctx.group(f"{mount.GetPath()}/Head", rotate=(0.0, -pitch, yaw))   # local +X = view direction
    hp = str(head.GetPath())
    ctx.box(hp, "Body", (0.13, 0.075, 0.075), (-0.075, 0, 0), body, collide=False)
    ctx.cyl(hp, "LensRing", 0.026, 0.012, "x", (-0.006, 0, 0), dark, collide=False)
    gap = ctx.spec["ceiling_height_m"] - z          # arm from the top of the housing body up to the ceiling
    bx, by = -0.075 * math.cos(math.radians(yaw)), -0.075 * math.sin(math.radians(yaw))
    arm_len = gap - 0.035
    ctx.cyl(str(mount.GetPath()), "Arm", 0.012, arm_len, "z", (bx, by, 0.035 + arm_len / 2), body, collide=False)
    ctx.cyl(str(mount.GetPath()), "CeilingPlate", 0.045, 0.01, "z", (bx, by, gap - 0.005), body, collide=False)


STREAM_SUFFIX = {"color": "RGB", "depth": "Depth"}


def stream_prim_name(rig: str, stream: str) -> str:
    """Camera prim of one stream of an RGB-D rig, unique in Isaac's camera menu: <rig>_RGB / <rig>_Depth."""
    return safe_name(f"{rig}_{STREAM_SUFFIX.get(stream, stream.title())}")


def _define_camera(stage, path, optics, clipping, focus_m=None):
    camera = UsdGeom.Camera.Define(stage, path)
    camera.CreateProjectionAttr().Set(UsdGeom.Tokens.perspective)
    camera.CreateFocalLengthAttr().Set(float(optics["focal_length_mm"]))
    camera.CreateHorizontalApertureAttr().Set(float(optics["horizontal_aperture_mm"]))
    camera.CreateVerticalApertureAttr().Set(float(optics["vertical_aperture_mm"]))
    camera.CreateClippingRangeAttr().Set(Gf.Vec2f(*[float(v) for v in clipping]))
    if focus_m:                                       # focused on the patient; fStop 0 = no depth-of-field blur
        camera.CreateFocusDistanceAttr().Set(float(focus_m))
        camera.CreateFStopAttr().Set(0.0)
    prim = camera.GetPrim()
    prim.CreateAttribute("sdg:resolution", Sdf.ValueTypeNames.Int2, custom=True).Set(Gf.Vec2i(*optics["resolution"]))
    set_custom(prim, "fov_h_deg", float(optics["fov_h_deg"]))
    set_custom(prim, "fov_v_deg", float(optics["fov_v_deg"]))
    return camera


def _build_rig(ctx, parent, name, cam, dark) -> str:
    """RGB-D camera: Xform with the look-at pose (camera frame: +X right, +Y up, -Z view) and one camera per stream,
    offset by its sensor position ([right, up, forward]); body + stand meshes in the room frame."""
    rig = UsdGeom.Xform.Define(ctx.stage, f"{parent}/{name}")
    rig.AddTransformOp().Set(look_at_matrix(cam["position"], cam["target"], cam.get("up", (0.0, 0.0, 1.0))))
    prim = rig.GetPrim()
    ctx.label(prim, "rgbd_camera")
    for key, value in (("rig", cam["rig"]), ("mount", cam["mount"]), ("attached_to", cam["attached_to"]),
                       ("orientation", cam["orientation"]), ("target", [float(v) for v in cam["target"]])):
        set_custom(prim, key, value)
    if cam.get("depth_range_m"):
        prim.CreateAttribute("sdg:depth_range_m", Sdf.ValueTypeNames.Float2, custom=True).Set(
            Gf.Vec2f(*[float(v) for v in cam["depth_range_m"]]))
    rp = str(prim.GetPath())
    for stream, optics in cam["streams"].items():
        c = _define_camera(ctx.stage, f"{rp}/{stream_prim_name(name, stream)}", optics, cam["clipping_range_m"],
                           cam.get("focus_distance_m"))
        ox, oy, oz = optics.get("offset_m") or (0.0, 0.0, 0.0)
        if any(abs(v) > 1e-12 for v in (ox, oy, oz)):
            c.AddTranslateOp().Set(Gf.Vec3d(float(ox), float(oy), -float(oz)))
        set_custom(c.GetPrim(), "stream", stream)
    if cam.get("stand", True) or cam.get("asset"):
        _rig_hardware(ctx, parent, name, cam, dark)
    return rp


def _rig_hardware(ctx, parent, name, cam, dark):
    """Camera body aligned with the view (+ lens rings) and its stand, in the room frame (no colliders)."""
    x, y, z = cam["position"]
    tx, ty, tz = cam["target"]
    yaw = math.degrees(math.atan2(ty - y, tx - x))
    pitch = math.degrees(math.atan2(tz - z, math.hypot(tx - x, ty - y)))
    roll = 90.0 if cam.get("orientation") == "portrait" else 0.0
    bw, bd, bh = cam.get("body_size_m", (0.124, 0.029, 0.026))
    mount = ctx.group(f"{parent}/{name}_Mount", translate=(x, y, z), label="camera_stand")
    mp = str(mount.GetPath())
    head = ctx.group(f"{mp}/Head", rotate=(roll, -pitch, yaw), label="rgbd_camera")   # local +X = view direction
    hp = str(head.GetPath())
    body = ctx.looks.color("#2a2d31", 0.45, metallic=0.3)
    if not ctx.reference_asset(f"{hp}/Body", cam.get("asset")):
        ctx.box(hp, "Body", (bd, bw, bh), (-bd / 2, 0, 0), body, collide=False)
        base = float(cam.get("baseline_m") or 0.095)
        for k, off in enumerate((-base / 2, base / 2)):
            ctx.cyl(hp, f"Lens{k}", 0.009, 0.004, "x", (0.001, off, 0), dark, collide=False)
    if not cam.get("stand", True):
        return
    metal = ctx.looks.get("Metal")
    kind, info = cam.get("stand_type"), cam.get("mount_info") or {}
    drop = bh / 2 + 0.005                      # stand meets the bottom of the body
    if kind == "tripod":
        col = z - drop
        ctx.cyl(mp, "Column", 0.012, col * 0.55, "z", (0, 0, -drop - col * 0.55 / 2), metal)   # floor stand collides
        ctx.box(mp, "Plate", (0.05, 0.05, 0.01), (0, 0, -drop + 0.005), dark, collide=False)
        rect = info.get("stand_rect")
        spread = (rect[2] - rect[0]) / 2 if rect else 0.27
        hub = col * 0.45                       # legs from the hub (column bottom) to the floor
        ctx.cyl(mp, "Hub", 0.02, 0.05, "z", (0, 0, -z + hub), dark, collide=False)
        length, tilt = math.hypot(spread, hub), math.degrees(math.atan2(spread, hub))
        for k in range(3):
            a = 120.0 * k + yaw
            ar = math.radians(a)
            leg = ctx.group(f"{mp}/Leg{k}", translate=(spread / 2 * math.cos(ar), spread / 2 * math.sin(ar), -z + hub / 2),
                            rotate=(0, -tilt, a))
            ctx.cyl(str(leg.GetPath()), "Tube", 0.009, length, "z", (0, 0, 0), metal)
    elif kind in ("bracket", "post_arm"):
        base_z = info.get("base_z", z - 0.1)
        px, py = info.get("post_xy", (x, y))
        dx, dy = px - x, py - y                # post position relative to the camera
        top = drop if kind == "post_arm" else -drop
        post_len = max(z + top - base_z, 0.01)
        ctx.cyl(mp, "Post", 0.011, post_len, "z", (dx, dy, base_z - z + post_len / 2), metal, collide=False)
        ctx.box(mp, "Foot", (0.05, 0.05, 0.008), (dx, dy, base_z - z + 0.004), dark, collide=False)
        if kind == "post_arm":                 # horizontal arm from the post top out over the camera
            arm = math.hypot(dx, dy)
            ang = math.degrees(math.atan2(dy, dx))
            g = ctx.group(f"{mp}/Arm", translate=(dx / 2, dy / 2, drop), rotate=(0, 0, ang))
            ctx.box(str(g.GetPath()), "Bar", (arm + 0.02, 0.025, 0.012), (0, 0, 0), metal, collide=False)
            ctx.cyl(mp, "Hanger", 0.008, drop, "z", (0, 0, drop / 2), metal, collide=False)
