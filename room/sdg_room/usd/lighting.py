"""Ceiling panel lights: UsdLux RectLight (diffuse, facing down) + emissive diffuser mesh per panel."""

import math

from pxr import Gf, UsdLux

from .stage import set_custom


def blackbody_rgb(kelvin: float):
    """Approximate sRGB of a black body (Tanner Helland fit), normalised to max 1 (diffuser tint only)."""
    t = kelvin / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = (99.4708025861 * math.log(t) - 161.1195681661) if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    rgb = [min(max(v, 0.0), 255.0) / 255.0 for v in (r, g, b)]
    m = max(rgb)
    return [v / m for v in rgb]


def build_lights(ctx, photometry: dict):
    spec, lay = ctx.spec, ctx.spec["layout"]
    H = spec["ceiling_height_m"]
    light_cfg = ctx.cfg["lighting"]
    tint = blackbody_rgb(spec["cct_k"])
    emissive = [c * light_cfg["panels"]["diffuser_emissive"] for c in tint]
    diffuser = ctx.looks.make("PanelDiffuser", color="#f4f4f4", roughness=0.6, emissive=emissive)
    frame = ctx.looks.color("#e4e4e0", 0.5)
    grp = ctx.group(f"{ctx.root}/Lights")
    g = str(grp.GetPath())
    paths = []
    for panel in lay["panels"]:
        (x, y), (sx, sy) = panel["center"], panel["size_m"]
        zone = photometry["exam"] if panel["zone"] == "exam" else photometry["changing"]
        pg = ctx.group(f"{g}/{panel['name']}", translate=(x, y, H), label="light_panel")
        pp = str(pg.GetPath())
        ctx.box(pp, "Frame", (sx + 0.03, sy + 0.03, 0.012), (0, 0, -0.006), frame, collide=False)
        ctx.box(pp, "Diffuser", (sx, sy, 0.004), (0, 0, -0.014), diffuser, collide=False)
        light = UsdLux.RectLight.Define(ctx.stage, f"{pp}/RectLight")
        light.AddTranslateOp().Set(Gf.Vec3d(0, 0, -0.017))          # just below the diffuser, emits along -Z
        light.CreateWidthAttr().Set(float(sx))
        light.CreateHeightAttr().Set(float(sy))
        light.CreateIntensityAttr().Set(float(zone["luminance_nits"]))
        light.CreateExposureAttr().Set(0.0)
        light.CreateNormalizeAttr().Set(False)
        light.CreateColorAttr().Set(Gf.Vec3f(1.0, 1.0, 1.0))
        light.CreateEnableColorTemperatureAttr().Set(True)
        light.CreateColorTemperatureAttr().Set(float(spec["cct_k"]))
        light.CreateDiffuseAttr().Set(1.0)
        light.CreateSpecularAttr().Set(1.0)
        set_custom(light.GetPrim(), "target_lux", float(zone["target_lux"]))
        paths.append(str(light.GetPath()))
    dome = float(light_cfg.get("ambient_dome", 0.0))
    if dome > 0:
        d = UsdLux.DomeLight.Define(ctx.stage, f"{g}/Ambient")
        d.CreateIntensityAttr().Set(dome)
        d.CreateEnableColorTemperatureAttr().Set(True)
        d.CreateColorTemperatureAttr().Set(float(spec["cct_k"]))
        paths.append(str(d.GetPath()))
    return paths
