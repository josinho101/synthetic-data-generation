"""Cameras: UsdGeom.Camera prims (look-at transform, optics) + optional wall housing / bracket meshes."""

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
