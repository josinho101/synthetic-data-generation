"""Corridor outside the entrance: floor slab (walkable, collider) and a ceiling-height panel light.

The patient pipeline (sdg) loads the patient in front of the entrance and walks them in and out, so the area outside
the suite needs a floor to stand on and light to be seen. The corridor is a rectangle in front of the entrance door:
`depth_m` out from the wall's outer face along the door's outward normal and `width_m` along the wall, centred on the
door. Its rect is stored on the root as `sdg:corridor_block` (room frame) like the check-in room annex.
"""

from pxr import Gf, Sdf, UsdLux

from .shell import FLOOR_T
from .stage import set_custom


def corridor_rect(spec, cfg) -> list:
    """[x0, y0, x1, y1] of the corridor floor in the room frame."""
    ent = spec["layout"]["entrance"]
    ccfg = cfg["room"].get("corridor") or {}
    depth, width = float(ccfg.get("depth_m", 3.0)), float(ccfg.get("width_m", 2.4))
    out = ent["out_normal"]
    outer = min(ent["plane"]) if (out[0] < 0 or out[1] < 0) else max(ent["plane"])    # wall face on the outside
    c = ent["center"]
    if ent["axis"] == "y":            # wall runs along y; corridor extends along x
        x0, x1 = (outer - depth, outer) if out[0] < 0 else (outer, outer + depth)
        return [x0, c[1] - width / 2, x1, c[1] + width / 2]
    y0, y1 = (outer - depth, outer) if out[1] < 0 else (outer, outer + depth)
    return [c[0] - width / 2, y0, c[0] + width / 2, y1]


def build_corridor(ctx, materials, photometry: dict):
    ccfg = ctx.cfg["room"].get("corridor") or {}
    if not ccfg.get("enabled", True):
        return None
    spec = ctx.spec
    x0, y0, x1, y1 = corridor_rect(spec, ctx.cfg)
    grp = ctx.group(f"{ctx.root}/Corridor")
    gp = str(grp.GetPath())
    floor = ctx.group(f"{gp}/Floor", label="floor")
    floor_mat, floor_uv = materials["floor"]
    ctx.box(str(floor.GetPath()), "FloorSlab", (x1 - x0, y1 - y0, FLOOR_T), ((x0 + x1) / 2, (y0 + y1) / 2, -FLOOR_T / 2),
            floor_mat, floor_uv)
    root = ctx.stage.GetPrimAtPath(ctx.root)
    root.CreateAttribute("sdg:corridor_block", Sdf.ValueTypeNames.Double4, custom=True).Set(Gf.Vec4d(x0, y0, x1, y1))

    lcfg = ccfg.get("light") or {}
    light_path = None
    if lcfg.get("enabled", True):
        sx, sy = lcfg.get("size_m", [1.2192, 0.6096])
        height = float(lcfg.get("height_m", spec["ceiling_height_m"]))
        exam_nits = photometry["exam"]["luminance_nits"]
        lg = ctx.group(f"{gp}/Light", translate=((x0 + x1) / 2, (y0 + y1) / 2, height), label="light_panel")
        light = UsdLux.RectLight.Define(ctx.stage, f"{lg.GetPath()}/RectLight")     # emits along -Z (down)
        light.CreateWidthAttr().Set(float(sx))
        light.CreateHeightAttr().Set(float(sy))
        light.CreateIntensityAttr().Set(float(exam_nits) * float(lcfg.get("relative_to_exam_panels", 1.0)))
        light.CreateExposureAttr().Set(0.0)
        light.CreateNormalizeAttr().Set(False)
        light.CreateEnableColorTemperatureAttr().Set(True)
        light.CreateColorTemperatureAttr().Set(float(spec["cct_k"]))
        light.CreateColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))                      # colour from the temperature
        set_custom(light.GetPrim(), "zone", "corridor")
        light_path = str(light.GetPath())
    return {"group": gp, "rect": [round(v, 4) for v in (x0, y0, x1, y1)], "light": light_path}
