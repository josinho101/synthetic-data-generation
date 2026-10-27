"""Hit the sampled target height (bisection on the Anny height phenotype), stand on the floor, measure mass/BMI."""

import logging

import numpy as np

_LOG = logging.getLogger("anny_humans.body_fit")


def body_extent(body, rest) -> tuple:
    z = rest.vertices[body.body_vertices, 2]
    return float(z.min()), float(z.max())


def body_volume_m3(body, points) -> float:
    """Volume enclosed by the body surface (helpers excluded): signed tetrahedra over its triangles."""
    tris = points[body.triangles(body.body_faces)]
    return float(abs(np.einsum("ij,ij->i", np.cross(tris[:, 0], tris[:, 1]), tris[:, 2]).sum()) / 6.0)


def solve_height(body, phenotypes: dict, local_changes: dict, target_cm: float, tolerance_cm: float,
                 max_iterations: int, max_uniform_scale: float) -> tuple:
    """-> (rest standing on z = 0, fit info). Bisection over height in [0, 1]; a small uniform scale finishes
    targets outside the phenotype's reach (bounded by max_uniform_scale)."""
    lo, hi = 0.0, 1.0
    best = None
    for iteration in range(max_iterations):
        value = 0.5 if iteration == 0 else (lo + hi) / 2.0
        rest = body.evaluate(dict(phenotypes, height=value), local_changes)
        z0, z1 = body_extent(body, rest)
        height_cm = (z1 - z0) * 100.0
        error = height_cm - target_cm
        _LOG.debug(f"height solver it={iteration} phenotype={value:.4f} height={height_cm:.2f}cm error={error:+.2f}")
        if best is None or abs(error) < abs(best[1] - target_cm):
            best = (value, height_cm, rest)
        if abs(error) <= tolerance_cm:
            break
        if error < 0:
            lo = value
        else:
            hi = value
    value, height_cm, rest = best
    z0, _ = body_extent(body, rest)
    rest = rest.translated([0.0, 0.0, -z0])                       # soles on the floor
    scale = 1.0
    if abs(height_cm - target_cm) > tolerance_cm:
        scale = float(np.clip(target_cm / height_cm, 1.0 - max_uniform_scale, 1.0 + max_uniform_scale))
        rest = rest.scaled(scale, [0.0, 0.0, 0.0])
        _LOG.info(f"height phenotype {value:.3f} reaches {height_cm:.1f}cm; uniform scale {scale:.4f} for "
                  f"target {target_cm}cm")
        z0, z1 = body_extent(body, rest)
        height_cm = (z1 - z0) * 100.0
    reached = abs(height_cm - target_cm) <= tolerance_cm
    if not reached:
        _LOG.warning(f"target height {target_cm}cm not reachable; clamped at {height_cm:.1f}cm")
    return rest, {"height_macro": round(value, 4), "height_scale": round(scale, 5),
                  "height_cm": round(height_cm, 2), "height_ok": reached}


def measure_mass(body, rest, density: float) -> dict:
    z0, z1 = body_extent(body, rest)
    height_m = z1 - z0
    volume = body_volume_m3(body, rest.vertices)
    mass = volume * density
    bmi = mass / (height_m ** 2)
    _LOG.info(f"volume={volume * 1000:.1f}L mass={mass:.1f}kg height={height_m * 100:.1f}cm BMI={bmi:.1f}")
    return {"volume_l": round(volume * 1000.0, 2), "weight_kg": round(mass, 2),
            "bmi": round(bmi, 2), "height_cm": round(height_m * 100.0, 2)}


def fit_body(body, spec: dict, local_changes: dict, pop_cfg: dict, body_cfg: dict) -> tuple:
    """-> (rest, fit result) for one spec (phenotypes = spec["macros"] with race flattened)."""
    macros = spec["macros"]
    phenotypes = {k: macros[k] for k in ("gender", "age", "muscle", "weight", "proportions", "cupsize", "firmness")}
    phenotypes.update({race: macros["race"][race] for race in ("african", "asian", "caucasian")})
    hcfg = pop_cfg["height_cm"]
    rest, result = solve_height(body, phenotypes, local_changes, float(spec["target_height_cm"]),
                                float(hcfg.get("tolerance_cm", 0.5)), int(hcfg.get("max_iterations", 12)),
                                float(body_cfg.get("max_uniform_scale", 0.06)))
    result.update(measure_mass(body, rest, float(pop_cfg.get("body_density_kg_m3", 1010))))
    lo, hi = pop_cfg.get("bmi_guard", [0, 999])
    result["bmi_ok"] = lo <= result["bmi"] <= hi
    if not result["bmi_ok"]:
        _LOG.warning(f"BMI {result['bmi']} outside guard [{lo}, {hi}]")
    result["fit_ok"] = result["height_ok"] and result["bmi_ok"]
    return rest, result
