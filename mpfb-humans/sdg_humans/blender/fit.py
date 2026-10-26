"""Hit the sampled target height (bisection on the MPFB height macro) and measure mass/BMI."""

import logging

import bpy

from . import body, geometry

_LOG = logging.getLogger("sdg_humans.blender.fit")


def measure_height_m(obj, body_indices) -> float:
    coords = geometry.evaluated_coords(obj)
    lo, hi = geometry.body_extent(coords, body_indices)
    return hi - lo


def put_feet_on_ground(obj, body_indices) -> None:
    coords = geometry.evaluated_coords(obj)
    lowest, _ = geometry.body_extent(coords, body_indices)
    obj.location.z -= lowest
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)  # also moves shape keys
    bpy.context.view_layer.update()


def solve_height(ns, obj, target_cm: float, tolerance_cm: float, max_iterations: int) -> dict:
    body_indices = geometry.group_vertex_indices(obj, "body")
    lo, hi = 0.0, 1.0
    best = None
    for iteration in range(max_iterations):
        value = 0.5 if iteration == 0 else (lo + hi) / 2.0
        body.set_macro(ns, obj, "height", value)
        height_cm = measure_height_m(obj, body_indices) * 100.0
        error = height_cm - target_cm
        _LOG.debug(f"height solver it={iteration} macro={value:.4f} height={height_cm:.2f}cm error={error:+.2f}")
        if best is None or abs(error) < abs(best[1] - target_cm):
            best = (value, height_cm)
        if abs(error) <= tolerance_cm:
            break
        if error < 0:
            lo = value
        else:
            hi = value
    value, height_cm = best
    body.set_macro(ns, obj, "height", value)
    reached = abs(height_cm - target_cm) <= tolerance_cm
    if not reached:
        _LOG.warning(f"target height {target_cm}cm not reachable; clamped at {height_cm:.1f}cm (macro {value:.3f})")
    put_feet_on_ground(obj, body_indices)
    return {"height_macro": round(value, 4), "height_cm": round(height_cm, 2), "height_ok": reached}


def measure_mass(obj, density: float) -> dict:
    body_indices = geometry.group_vertex_indices(obj, "body")
    coords = geometry.evaluated_coords(obj)
    lo, hi = geometry.body_extent(coords, body_indices)
    height_m = hi - lo
    volume = geometry.body_volume_m3(obj, coords, body_indices)
    mass = volume * density
    bmi = mass / (height_m ** 2)
    _LOG.info(f"volume={volume * 1000:.1f}L mass={mass:.1f}kg height={height_m * 100:.1f}cm BMI={bmi:.1f}")
    return {"volume_l": round(volume * 1000.0, 2), "weight_kg": round(mass, 2),
            "bmi": round(bmi, 2), "height_cm": round(height_m * 100.0, 2)}


def fit_body(ns, obj, spec: dict, pop_cfg: dict) -> dict:
    hcfg = pop_cfg["height_cm"]
    result = solve_height(ns, obj, float(spec["target_height_cm"]), float(hcfg.get("tolerance_cm", 0.5)),
                          int(hcfg.get("max_iterations", 12)))
    result.update(measure_mass(obj, float(pop_cfg.get("body_density_kg_m3", 1010))))
    lo, hi = pop_cfg.get("bmi_guard", [0, 999])
    result["bmi_ok"] = lo <= result["bmi"] <= hi
    if not result["bmi_ok"]:
        _LOG.warning(f"BMI {result['bmi']} outside guard [{lo}, {hi}]")
    result["fit_ok"] = result["height_ok"] and result["bmi_ok"]
    return result
