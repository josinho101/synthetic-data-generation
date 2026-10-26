"""Isaac-Sim compatibility checks on an exported human USD (usd-core / pxr)."""

import json
from pathlib import Path


def _skinned_z_range(stage, root_prim, mesh_filter=None):
    """z range of skinned mesh points at the default time (exact, unlike UsdSkel's padded bbox).
    mesh_filter(prim) -> bool restricts the meshes (e.g. the body only)."""
    from pxr import Usd, UsdGeom, UsdSkel, Gf, Vt

    cache = UsdSkel.Cache()
    root = UsdSkel.Root(root_prim)
    cache.Populate(root, Usd.TraverseInstanceProxies())
    z_lo, z_hi, posed = None, None, 0
    for binding in cache.ComputeSkelBindings(root, Usd.TraverseInstanceProxies()):
        query = cache.GetSkelQuery(binding.GetSkeleton())
        xforms = query.ComputeSkinningTransforms(Usd.TimeCode.Default())
        posed = max(posed, sum(1 for m in xforms if not Gf.IsClose(m, Gf.Matrix4d(1.0), 1e-4)))
        for target in binding.GetSkinningTargets():
            if mesh_filter is not None and not mesh_filter(target.GetPrim()):
                continue
            points = Vt.Vec3fArray(UsdGeom.Mesh(target.GetPrim()).GetPointsAttr().Get())
            target.ComputeSkinnedPoints(xforms, points, Usd.TimeCode.Default())
            to_world = UsdGeom.Xformable(binding.GetSkeleton().GetPrim()).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default())
            zs = [to_world.Transform(Gf.Vec3d(*p))[2] for p in points]
            z_lo = min(zs) if z_lo is None else min(z_lo, min(zs))
            z_hi = max(zs) if z_hi is None else max(z_hi, max(zs))
    return z_lo, z_hi, posed


def validate_usd(usd_path, metadata_path=None, landmark_prefix: str = "LM_", max_influences: int = 4,
                 height_tolerance_cm: float = 1.5) -> dict:
    from pxr import Sdf, Usd, UsdGeom, UsdShade, UsdSkel

    usd_path = Path(usd_path)
    errors, warnings = [], []
    stage = Usd.Stage.Open(str(usd_path))
    if stage is None:
        return {"status": "failed", "errors": [f"cannot open {usd_path}"], "warnings": []}

    if UsdGeom.GetStageUpAxis(stage) != UsdGeom.Tokens.z:
        errors.append(f"upAxis is {UsdGeom.GetStageUpAxis(stage)}, expected Z")
    if abs(UsdGeom.GetStageMetersPerUnit(stage) - 1.0) > 1e-6:
        errors.append(f"metersPerUnit is {UsdGeom.GetStageMetersPerUnit(stage)}, expected 1.0")
    default = stage.GetDefaultPrim()
    if not default:
        errors.append("no defaultPrim")

    roots = [p for p in stage.Traverse() if p.IsA(UsdSkel.Root)]
    skeletons = [p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton)]
    if len(roots) != 1:
        errors.append(f"expected exactly 1 SkelRoot, found {len(roots)}")
    if len(skeletons) != 1:
        errors.append(f"expected exactly 1 Skeleton, found {len(skeletons)}")
    joints = list(UsdSkel.Skeleton(skeletons[0]).GetJointsAttr().Get() or []) if skeletons else []
    landmark_joints = [j for j in joints if j.split("/")[-1].startswith(landmark_prefix)]

    meshes = [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]
    if not meshes:
        errors.append("no meshes")
    for mesh in meshes:
        binding = UsdSkel.BindingAPI(mesh)
        indices = binding.GetJointIndicesPrimvar()
        if not mesh.HasAPI(UsdSkel.BindingAPI) or not indices or not indices.IsDefined():
            errors.append(f"{mesh.GetPath()}: not skinned (missing SkelBindingAPI / jointIndices)")
        elif indices.GetElementSize() > max_influences:
            errors.append(f"{mesh.GetPath()}: {indices.GetElementSize()} influences > {max_influences}")
        if not UsdShade.MaterialBindingAPI(mesh).ComputeBoundMaterial()[0]:
            subsets = UsdGeom.Subset.GetAllGeomSubsets(UsdGeom.Imageable(mesh))
            if not subsets:
                warnings.append(f"{mesh.GetPath()}: no bound material")

    for prim in stage.Traverse():
        if prim.GetTypeName() == "Shader":
            attr = prim.GetAttribute("inputs:file")
            value = attr.Get() if attr else None
            if isinstance(value, Sdf.AssetPath) and value.path:
                resolved = (usd_path.parent / value.path).resolve()
                if not resolved.exists():
                    errors.append(f"missing texture {value.path}")

    height_cm = None
    if roots and skeletons:
        z_lo, z_hi, posed = _skinned_z_range(stage, roots[0])
        if posed:
            warnings.append(f"{posed} joints have non-identity skinning transforms (rest pose != bind pose)")
        if z_lo is not None and abs(z_lo) > 0.01:
            warnings.append(f"lowest point (incl. footwear) at z={z_lo:.3f} m (expected ~0)")
        human_id = default.GetName() if default else ""
        b_lo, b_hi, _ = _skinned_z_range(stage, roots[0], lambda p: p.GetParent().GetName() == human_id)
        if b_hi is not None:
            height_cm = round(b_hi * 100.0, 2)   # top of the head above the floor (feet may be hidden in shoes)

    expected = {}
    if metadata_path and Path(metadata_path).exists():
        meta = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        expected = {info["usd_joint"] for info in meta.get("landmarks", {}).values()}
        missing = sorted(expected - set(joints))
        if missing:
            errors.append(f"{len(missing)} landmark joints from metadata missing in USD, e.g. {missing[:3]}")
        body = meta.get("body", {})
        stature = body.get("height_cm")
        expected = (stature or 0) + float(body.get("footwear_lift_cm", 0.0))
        if stature and height_cm and abs(height_cm - expected) > height_tolerance_cm:
            warnings.append(f"USD head height {height_cm} cm differs from stature + footwear {expected:.2f} cm")

    status = "failed" if errors else ("warn" if warnings else "ok")
    return {"status": status, "errors": errors, "warnings": warnings, "joint_count": len(joints),
            "landmark_joint_count": len(landmark_joints), "mesh_count": len(meshes), "bounds_height_cm": height_cm}
