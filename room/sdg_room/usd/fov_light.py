"""Collimator field (FOV) light: a DiskLight at the collimator whose IES profile lights only the rectangular X-ray field.

Real collimators project a lit rectangle (the field the X-rays will cover) onto the patient. RTX's spotlight cone on
area lights does not produce that, so the light carries a generated IES (LM-63) profile: full intensity inside the
field's half-angles atan(field / 2 / SID), soft edge `edge_deg`, zero outside. It is created invisible (switched on
by the patient pipeline during an exposure) and moves with the tube head.
"""

import math

from pxr import Gf, Sdf, UsdGeom, UsdLux

from .stage import set_custom


def write_rect_ies(path, half_w_deg, half_h_deg, candela=1000.0, edge_deg=0.4, v_step=0.25, h_step=2.5) -> None:
    """IES LM-63 (type C) profile: candela inside |tan(theta) cos(phi)| <= tan(half_w), |tan(theta) sin(phi)| <=
    tan(half_h) around the light's axis (phi = 0 along the light's +X), linear soft edge, 0 outside."""
    ta, tb = math.tan(math.radians(half_w_deg)), math.tan(math.radians(half_h_deg))
    vmax = math.degrees(math.atan(math.hypot(ta, tb))) + 3.0
    vs = [round(i * v_step, 4) for i in range(int(vmax / v_step) + 2)] + [90.0]
    hs = [round(i * h_step, 4) for i in range(int(360 / h_step) + 1)]
    soft = math.radians(edge_deg)
    lines = ["IESNA:LM-63-2002", "[TEST] sdg_room collimator field light", "TILT=NONE",
             f"1 -1 1 {len(vs)} {len(hs)} 1 2 0.02 0.02 0", "1 1 0",
             " ".join(f"{v:g}" for v in vs), " ".join(f"{h:g}" for h in hs)]
    for h in hs:
        row = []
        for v in vs:
            t = math.tan(math.radians(min(v, 89.9)))
            x, y = abs(t * math.cos(math.radians(h))), abs(t * math.sin(math.radians(h)))
            fx = min(1.0, max(0.0, (ta - x) / soft + 0.5))
            fy = min(1.0, max(0.0, (tb - y) / soft + 0.5))
            row.append(f"{candela * fx * fy:.2f}")
        lines.append(" ".join(row))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def build_fov_light(ctx, collimator_path: str, front_y: float, sid_m: float):
    """FOVLight under the collimator, emitting along the beam (+Y of the tube head). Returns its path or None."""
    cfg = (ctx.cfg["equipment"]["tube_stand"].get("fov_light") or {})
    if not cfg.get("enabled", True):
        return None
    width_m, height_m = (float(v) / 100.0 for v in cfg.get("field_cm", [35.0, 43.0]))
    half_w = math.degrees(math.atan(width_m / 2 / sid_m))
    half_h = math.degrees(math.atan(height_m / 2 / sid_m))
    ctx.texture_dir.mkdir(parents=True, exist_ok=True)
    ies_name = "fov_field.ies"
    write_rect_ies(ctx.texture_dir / ies_name, half_w, half_h, edge_deg=float(cfg.get("edge_deg", 0.4)))
    light = UsdLux.DiskLight.Define(ctx.stage, f"{collimator_path}/FOVLight")
    xf = UsdGeom.Xformable(light)
    xf.AddTranslateOp().Set(Gf.Vec3d(0.0, front_y + float(cfg.get("offset_m", 0.03)), 0.0))
    xf.AddRotateXOp().Set(90.0)                       # DiskLight emits along -Z -> along the beam (+Y)
    light.CreateRadiusAttr().Set(float(cfg.get("radius_m", 0.01)))
    light.CreateIntensityAttr().Set(float(cfg.get("intensity", 200000.0)))
    light.CreateExposureAttr().Set(0.0)
    light.CreateColorAttr().Set(Gf.Vec3f(*cfg.get("color", [1.0, 0.96, 0.82])))
    shaping = UsdLux.ShapingAPI.Apply(light.GetPrim())
    shaping.CreateShapingIesFileAttr().Set(Sdf.AssetPath(f"./{ctx.texture_rel}/{ies_name}"))
    shaping.CreateShapingIesNormalizeAttr().Set(False)
    UsdGeom.Imageable(light).MakeInvisible()         # off until an exposure
    prim = light.GetPrim()
    set_custom(prim, "role", "fov_light")
    prim.CreateAttribute("sdg:field_cm", Sdf.ValueTypeNames.Float2, custom=True).Set(
        Gf.Vec2f(width_m * 100.0, height_m * 100.0))
    set_custom(prim, "sid_m", float(sid_m))
    return str(light.GetPath())
