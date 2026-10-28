"""Rewrite an exported human USD in place so the fitted Z-Anatomy skeleton is its rig (usd-core only).

  * Skeleton joints -> SkelOrigin + the Z-Anatomy anatomical bones only (fitted rigid frames as bind / rest
    transforms; `rig_parent_overrides` re-parents bones, e.g. radius under ulna). The MPFB rig and its LM_ / AN_
    landmark joints are dropped (keep_landmark_joints: true re-parents
    the landmark joints to an anatomical bone instead, world bind unchanged)
  * every skinned mesh (body, clothes, hair, eyes, ...) re-weighted MakeHuman -> anatomical (weights.py).
    Points, topology, UVs and materials are not touched.
  * old bone_* prims removed; the fitted Z-Anatomy meshes added under <SkelRoot>/ZAnatomy as bone_<name> /
    teeth_*, rigid to their bone, with one bone material
  * CC BY-SA attribution in the layer's customLayerData
"""

import logging

import numpy as np

from .weights import anatomical_bone, nearest_vertebra, remap, spine_polyline

_LOG = logging.getLogger("sdg_humans.skeleton.zanatomy")
ATTRIBUTION = ("Bone meshes: Z-Anatomy (z-anatomy.com, github.com/LluisV/Z-Anatomy), CC BY-SA 4.0, derived from "
               "BodyParts3D (DBCLS, CC BY-SA). Human: mpfb-humans (MakeHuman / MPFB, CC0).")


def _gf(m):
    from pxr import Gf
    return Gf.Matrix4d(*np.asarray(m, dtype=np.float64).T.ravel().tolist())     # column-vector math -> USD rows


def _np(m) -> np.ndarray:
    return np.array(m, dtype=np.float64).T


def rig_parents(names, parent, overrides: dict) -> np.ndarray:
    """Parent indices of the USD rig: the reference parents with `overrides` {bone: new parent bone} applied.

    The default override puts radius under ulna (humerus -> ulna -> radius -> carpus): with both forearm bones under
    the humerus, one animated forearm joint cannot bend both, and the skin of the other tears at the elbow. A parent
    must come before its child in the joint order (UsdSkel topology)."""
    parent = np.array(parent, dtype=int)
    index = {n: i for i, n in enumerate(names)}
    for child, new_parent in overrides.items():
        if child not in index or new_parent not in index:
            raise ValueError(f"skeleton.zanatomy.rig_parent_overrides: unknown bone {child!r} -> {new_parent!r}")
        if index[new_parent] >= index[child]:
            raise ValueError(f"skeleton.zanatomy.rig_parent_overrides: {new_parent} must come before {child} in the "
                             f"reference joint order")
        parent[index[child]] = index[new_parent]
    return parent


def rewrite(usd_path, ref, fit: dict, layer_cfg: dict, landmark_prefixes=("LM_", "AN_")) -> dict:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdSkel, Vt

    names, parent, maps = ref.names, ref.parent, ref.maps
    W, S = fit["W"], fit["S"]
    Minv = np.linalg.inv(ref.frames)
    stage = Usd.Stage.Open(str(usd_path))
    skel_prim = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton))
    skel_root = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Root))
    skel = UsdSkel.Skeleton(skel_prim)
    old_joints = [str(j) for j in skel.GetJointsAttr().Get()]
    old_bind = [_np(m) for m in skel.GetBindTransformsAttr().Get()]
    old_leaf = [j.split("/")[-1] for j in old_joints]
    poly = spine_polyline(W, names, maps)

    # anatomical joints (rig_parent_overrides re-parents joints in the USD rig only; the fit is not affected)
    parent = rig_parents(names, parent, layer_cfg.get("rig_parent_overrides") or {})
    paths = {}
    for i, n in enumerate(names):
        paths[n] = (paths[names[parent[i]]] + "/" if parent[i] >= 0 else "SkelOrigin/") + n
    new_joints = ["SkelOrigin"] + [paths[n] for n in names]
    bind = [np.eye(4)] + [W[i] for i in range(len(names))]
    parent_of = {"SkelOrigin": None} | {paths[n]: (paths[names[parent[i]]] if parent[i] >= 0 else "SkelOrigin")
                                        for i, n in enumerate(names)}
    # landmark joints (MPFB): dropped, or with keep_landmark_joints kept under the anatomical bone that now moves
    # their old MakeHuman parent
    moved, keep_lm = {}, bool(layer_cfg.get("keep_landmark_joints", False))
    for j, leaf, B in zip(old_joints, old_leaf, old_bind):
        if not leaf.startswith(tuple(landmark_prefixes)):
            continue
        if not keep_lm:
            moved[j] = None
            continue
        old_parent = j.rsplit("/", 1)[0] if "/" in j else ""
        if old_parent in moved:
            new_parent = moved[old_parent]
        else:
            pleaf = old_parent.split("/")[-1]
            if pleaf in set(maps["spine_split"]):
                bone = max(nearest_vertebra(B[:3, 3], poly), key=lambda x: x[1])[0]
            elif pleaf in ("SkelOrigin", "root", ""):
                bone = "pelvis"
            else:
                bone = anatomical_bone(pleaf, maps) or "pelvis"
            new_parent = paths[bone]
        moved[j] = f"{new_parent}/{leaf}"
        new_joints.append(moved[j])
        bind.append(B)
        parent_of[moved[j]] = new_parent
    index = {p: i for i, p in enumerate(new_joints)}
    rest = [bind[i] if parent_of[p] is None else np.linalg.inv(bind[index[parent_of[p]]]) @ bind[i]
            for i, p in enumerate(new_joints)]
    for attr in list(skel_prim.GetAttributes()):          # per-joint arrays of the old rig would no longer match
        v = attr.Get()
        if attr.GetName().startswith("primvars:") and hasattr(v, "__len__") and not isinstance(v, str) \
                and len(v) == len(old_joints):
            skel_prim.RemoveProperty(attr.GetName())
    skel.GetJointsAttr().Set(Vt.TokenArray(new_joints))
    skel.GetBindTransformsAttr().Set(Vt.Matrix4dArray([_gf(m) for m in bind]))
    skel.GetRestTransformsAttr().Set(Vt.Matrix4dArray([_gf(m) for m in rest]))
    if skel.GetJointNamesAttr().HasAuthoredValue():
        skel.GetJointNamesAttr().Set(Vt.TokenArray([j.split("/")[-1] for j in new_joints]))
    joint_index = {n: i + 1 for i, n in enumerate(names)}

    # re-skin every MakeHuman-weighted mesh
    reskinned, dropped = [], 0.0
    max_inf = int(layer_cfg.get("max_influences", 4))
    for prim in list(Usd.PrimRange(skel_root)):
        if not prim.IsA(UsdGeom.Mesh) or prim.GetName().startswith(("bone_", "teeth_")):
            continue
        bapi = UsdSkel.BindingAPI(prim)
        ji, jw = bapi.GetJointIndicesPrimvar(), bapi.GetJointWeightsPrimvar()
        if not (ji and ji.HasValue()):
            continue
        k = ji.GetElementSize()
        I = np.array(ji.Get()).reshape(-1, k)
        Wv = np.array(jw.Get()).reshape(-1, k)
        own = bapi.GetJointsAttr()
        leafs = [str(j).split("/")[-1] for j in own.Get()] if own and own.HasAuthoredValue() else old_leaf
        pts = np.array(UsdGeom.Mesh(prim).GetPointsAttr().Get(), dtype=np.float64)
        G = bapi.GetGeomBindTransformAttr().Get()
        if G is not None:
            Gm = _np(G)
            pts = pts @ Gm[:3, :3].T + Gm[:3, 3]
        constant = ji.GetInterpolation() == UsdGeom.Tokens.constant
        if constant:
            I, Wv, pts = I[:1], Wv[:1], pts.mean(0, keepdims=True)
        nI, nW, dw = remap(I, Wv, leafs, pts, maps, poly, joint_index, max_inf)
        dropped += dw
        ji.Set(Vt.IntArray(nI.ravel().tolist()))
        ji.SetElementSize(max_inf)
        jw.Set(Vt.FloatArray(nW.ravel().tolist()))
        jw.SetElementSize(max_inf)
        if own and own.HasAuthoredValue():
            own.Set(Vt.TokenArray(new_joints))
        reskinned.append(prim.GetName())

    # bones: old ones out, Z-Anatomy in (with one bone material)
    removed = [p.GetPath() for p in Usd.PrimRange(skel_root) if p.GetName().startswith("bone_")
               and not p.GetParent().GetName().startswith("bone_")]     # top-most only (removes the children)
    for pth in removed:
        stage.RemovePrim(pth)
    group = UsdGeom.Xform.Define(stage, skel_root.GetPath().AppendChild("ZAnatomy"))
    mat = UsdShade.Material.Define(stage, group.GetPath().AppendPath("Looks/ZAnatomyBone"))
    sh = UsdShade.Shader.Define(stage, mat.GetPath().AppendChild("PreviewSurface"))
    sh.CreateIdAttr("UsdPreviewSurface")
    rgb = layer_cfg.get("bone_color_rgb", [0.93, 0.9, 0.82])
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    entries, tris = [], 0
    for key in ref.mesh_keys:
        X, F, owner = ref.mesh(key)
        b = names.index(owner)
        loc = (np.c_[X, np.ones(len(X))] @ Minv[b].T)[:, :3] * S[b]
        Xp = loc @ W[b][:3, :3].T + W[b][:3, 3]
        m = UsdGeom.Mesh.Define(stage, group.GetPath().AppendChild(key))
        m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(Xp.astype(np.float32)))
        m.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(F)))
        m.CreateFaceVertexIndicesAttr(Vt.IntArray(F.ravel().tolist()))
        m.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
        m.CreateExtentAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*Xp.min(0)), Gf.Vec3f(*Xp.max(0))]))
        UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(mat)
        bb = UsdSkel.BindingAPI.Apply(m.GetPrim())
        bb.CreateSkeletonRel().SetTargets([skel_prim.GetPath()])
        bb.CreateJointsAttr().Set(Vt.TokenArray([paths[owner]]))
        bb.CreateJointIndicesPrimvar(constant=True, elementSize=1).Set(Vt.IntArray([0]))
        bb.CreateJointWeightsPrimvar(constant=True, elementSize=1).Set(Vt.FloatArray([1.0]))
        bb.CreateGeomBindTransformAttr().Set(Gf.Matrix4d(1.0))
        tris += len(F)
        entries.append({"name": key[5:] if key.startswith("bone_") else key, "object": key, "rig_bone": owner,
                        "part": "zanatomy", "vertices": int(len(X)), "usd_prim": str(m.GetPath())})
    data = dict(stage.GetRootLayer().customLayerData)
    data.update({"zanatomy:attribution": ATTRIBUTION, "zanatomy:license_bones": "CC-BY-SA-4.0",
                 "zanatomy:reference": ref.version})
    stage.GetRootLayer().customLayerData = data
    stage.GetRootLayer().Save()
    return {"joints": len(new_joints), "anatomical_joints": len(names),
            "landmark_joints": sum(1 for v in moved.values() if v),
            "joint_paths": moved, "reskinned_meshes": reskinned, "removed_bone_prims": len(removed),
            "bone_meshes": entries, "bone_triangles": tris, "dropped_weight": round(float(dropped), 4),
            "skeleton_prim": str(skel_prim.GetPath())}
