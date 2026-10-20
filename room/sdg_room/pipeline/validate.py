"""USD validation for Isaac Sim (usd-core): units, axis, default prim, required parts, textures, bounds, materials,
semantics and colliders."""

from pathlib import Path

from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade

from ..placement import FACING

REQUIRED = ["Shell/Floor", "Shell/Walls", "Shell/Ceiling", "Shell/Doors/Entrance", "CheckIn/Door", "CheckIn/Bench",
            "Equipment/WallStand", "Equipment/TubeStand", "Markers/PatientStand"]
# parts (and their semantic classes) that exist only when the equipment is procedural (no `asset:` override)
REQUIRED_PROCEDURAL = {
    "Equipment/WallStand": (["Equipment/WallStand/Carriage/Detector/Handles",
                             "Equipment/WallStand/Carriage/Detector/ActiveArea"], ["wall_detector", "detector_handle"]),
    "Equipment/TubeStand": (["Equipment/TubeStand/Rail", "Equipment/TubeStand/Carriage/Arm/TubeHead"], ["xray_tube"]),
}


def _texture_files(stage):
    for prim in stage.Traverse():
        if prim.IsA(UsdShade.Shader):
            inp = UsdShade.Shader(prim).GetInput("file")
            if inp and inp.Get() is not None:
                yield prim, inp.Get()


def _room_frame(stage, root):
    """Matrix stage -> room frame (inverse of the root placement transform)."""
    return UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).GetInverse()


def _check_placement(stage, root, errors):
    facing, outward = root.GetAttribute("sdg:door_facing").Get(), root.GetAttribute("sdg:entrance_outward_room").Get()
    if facing is None or outward is None:
        errors.append("root prim has no sdg:door_facing / sdg:entrance_outward_room (placement missing)")
        return
    m = UsdGeom.Xformable(root).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    d = m.TransformDir(Gf.Vec3d(*outward))
    want = FACING[facing]
    if abs(d[0] - want[0]) > 1e-4 or abs(d[1] - want[1]) > 1e-4:
        errors.append(f"entrance faces {tuple(round(v, 3) for v in d)} on the stage, expected {facing}")


def _check_cameras(stage, root, cameras, footprint_m, errors):
    to_room = _room_frame(stage, root)
    for cam in cameras or []:
        prim = stage.GetPrimAtPath(f"{root.GetPath()}/Cameras/{cam['name']}")
        if not prim or not prim.IsA(UsdGeom.Camera):
            errors.append(f"camera {cam['name']} missing")
            continue
        m = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()) * to_room
        eye = m.ExtractTranslation()
        view = m.TransformDir(Gf.Vec3d(0, 0, -1)).GetNormalized()
        to_target = (Gf.Vec3d(*cam["target"]) - eye).GetNormalized()
        if Gf.Dot(view, to_target) < 0.9:
            errors.append(f"camera {cam['name']} does not look at its target")
        if cam.get("zone") in ("room", "checkin") and footprint_m:
            L, W = footprint_m
            if not (0 < eye[0] < L and 0 < eye[1] < W):
                errors.append(f"camera {cam['name']} outside the room at {tuple(round(v, 3) for v in eye)}")


def validate_usd(usd_path, footprint_m=None, ceiling_m=None, wall_t=0.12, expect_semantics=True,
                 expect_colliders=True, cameras=None) -> dict:
    errors, warnings = [], []
    usd_path = Path(usd_path)
    stage = Usd.Stage.Open(str(usd_path))
    if stage is None:
        return {"status": "failed", "errors": [f"cannot open {usd_path}"], "warnings": []}
    if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        errors.append("upAxis is not Z")
    if abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-9:
        errors.append(f"metersPerUnit = {UsdGeom.GetStageMetersPerUnit(stage)} (expected 1.0)")
    root = stage.GetDefaultPrim()
    if not root:
        errors.append("no defaultPrim")
        return {"status": "failed", "errors": errors, "warnings": warnings}
    rp = str(root.GetPath())
    required, classes_needed = list(REQUIRED), ["floor", "wall", "floor_marker", "door"]
    for part, (prims, classes) in REQUIRED_PROCEDURAL.items():
        part_prim = stage.GetPrimAtPath(f"{rp}/{part}")
        if part_prim and not part_prim.HasAuthoredReferences():
            required += prims
            classes_needed += classes
    for rel in required:
        if not stage.GetPrimAtPath(f"{rp}/{rel}"):
            errors.append(f"missing prim {rp}/{rel}")
    lights = [p for p in stage.Traverse() if p.IsA(UsdLux.RectLight)]
    if not lights:
        errors.append("no RectLight")
    for prim, asset in _texture_files(stage):
        resolved = asset.resolvedPath or str((usd_path.parent / asset.path).resolve())
        if not Path(resolved).exists():
            errors.append(f"texture missing: {asset.path} ({prim.GetPath()})")

    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    unbound = [str(p.GetPath()) for p in meshes if not UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()[0]]
    if unbound:
        errors.append(f"{len(unbound)} meshes without material, e.g. {unbound[:3]}")
    if expect_colliders:
        n_col = sum(1 for p in meshes if p.HasAPI(UsdPhysics.CollisionAPI))
        if n_col == 0:
            errors.append("no colliders")
        elif n_col < len(meshes) * 0.5:
            warnings.append(f"only {n_col}/{len(meshes)} meshes have colliders")
    if expect_semantics:
        labelled = [p for p in stage.Traverse() if p.HasAttribute("semantics:labels:class")]
        classes = {p.GetAttribute("semantics:labels:class").Get()[0] for p in labelled}
        for needed in classes_needed:
            if needed not in classes:
                errors.append(f"semantic class '{needed}' missing")

    _check_placement(stage, root, errors)
    _check_cameras(stage, root, cameras, footprint_m, errors)
    # bounds in the room frame (the root carries the stage placement)
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    box = cache.ComputeUntransformedBound(root).ComputeAlignedRange()
    lo, hi = box.GetMin(), box.GetMax()
    bounds = {"min": [round(v, 4) for v in lo], "max": [round(v, 4) for v in hi]}
    if footprint_m:
        L, W = footprint_m
        tol = wall_t + 0.02
        if lo[0] < -tol or lo[1] < -tol or hi[0] > L + tol or hi[1] > W + tol:
            errors.append(f"bounds {bounds} exceed the footprint {L:.3f} x {W:.3f} m + walls")
    floor = stage.GetPrimAtPath(f"{rp}/Shell/Floor")
    if floor:
        ftop = cache.ComputeRelativeBound(floor, root).ComputeAlignedRange().GetMax()[2]
        if abs(ftop) > 1e-4:
            errors.append(f"floor top at z = {ftop:.4f} (expected 0)")
    if ceiling_m and hi[2] > ceiling_m + 0.06:
        warnings.append(f"geometry above the ceiling slab: max z {hi[2]:.3f}")
    status = "failed" if errors else ("warn" if warnings else "ok")
    return {"status": status, "errors": errors, "warnings": warnings, "bounds": bounds, "meshes": len(meshes),
            "lights": len(lights)}
