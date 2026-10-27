"""Write one human as a rigged UsdSkel asset for Isaac Sim (metres, Z up, facing -Y, rest A-pose).

Same prim layout as the MPFB pipeline, so sdg/ and usd_post work unchanged:

/<ID>                          Xform (defaultPrim)
├── <ID>_rig                   SkelRoot
│   ├── <ID>_rig               Skeleton: SkelOrigin (identity, at the origin) / root / ... 163 rig joints,
│   │                          then the non-deforming LM_* landmark and AN_* frame joints
│   ├── <ID>/base              Mesh: body (13380-vertex hm08 body, helpers removed)
│   ├── <ID>_eyes/<mesh>       eyes, <ID>_<hair asset>, <ID>_<eyebrow>, <ID>_<eyelashes>
│   ├── <ID>_<garment asset>/<mesh>    one per garment
│   └── bone_<name>/bone_<name>        anatomical bone meshes (purpose set by usd_post)
└── _materials/<name>          UsdPreviewSurface (+ MDL OmniSurface for RTX)

Every mesh is skinned (jointIndices / jointWeights, geomBindTransform identity) and has smooth vertex normals.
"""

import logging

import numpy as np
from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade, UsdSkel, Vt

from .geometry import triangulate, vertex_normals
from .model import usd_name

_LOG = logging.getLogger("anny_humans.usd_writer")


def _gf(m):
    return Gf.Matrix4d(np.asarray(m, dtype=np.float64).T.tolist())    # numpy column convention -> USD rows


def joint_paths(names, parents) -> list:
    paths = []
    for name, parent in zip(names, parents):
        paths.append(name if parent < 0 else f"{paths[parent]}/{name}")
    return paths


# ---------------------------------------------------------------------------------------------- materials
def _texture(stage, material, name: str, file: str, colorspace: str, output: str, st_reader):
    tex = UsdShade.Shader.Define(stage, material.GetPath().AppendChild(name))
    tex.CreateIdAttr("UsdUVTexture")
    tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(f"textures/{file}")
    tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(colorspace)
    tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
    tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
    tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(st_reader.ConnectableAPI(), "result")
    tex.CreateOutput(output, Sdf.ValueTypeNames.Float3 if output in ("rgb",) else Sdf.ValueTypeNames.Float)
    return tex


def _preview_surface(stage, material, spec: dict):
    shader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("preview"))
    shader.CreateIdAttr("UsdPreviewSurface")
    st = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("st_reader"))
    st.CreateIdAttr("UsdPrimvarReader_float2")
    st.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
    st.CreateOutput("result", Sdf.ValueTypeNames.Float2)
    color = Gf.Vec3f(*map(float, spec.get("color") or (0.5, 0.5, 0.5)))
    if spec.get("kind") == "vertex_color":
        reader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("color_reader"))
        reader.CreateIdAttr("UsdPrimvarReader_float3")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("displayColor")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float3)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(reader.ConnectableAPI(), "result")
    elif spec.get("diffuse"):
        tex = _texture(stage, material, "diffuse_texture", spec["diffuse"], "sRGB", "rgb", st)
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
        if spec.get("opacity_cutout"):
            tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "a")
            shader.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.5)
    else:
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    if spec.get("roughness_map"):
        tex = _texture(stage, material, "roughness_texture", spec["roughness_map"], "raw", "r", st)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(tex.ConnectableAPI(), "r")
    else:
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(spec.get("roughness", 0.6)))
    if spec.get("normal"):
        tex = _texture(stage, material, "normal_texture", spec["normal"], "raw", "rgb", st)
        tex.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
        tex.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
        shader.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(tex.ConnectableAPI(), "rgb")
    shader.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.04, 0.04, 0.04))
    shader.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")


def _mdl_asset(shader, name: str, file: str, colorspace: str):
    attr = shader.CreateInput(name, Sdf.ValueTypeNames.Asset)
    attr.Set(Sdf.AssetPath(f"./textures/{file}"))
    attr.GetAttr().SetColorSpace(colorspace)


def _omni_surface(stage, material, spec: dict) -> None:
    """MDL OmniSurface (Isaac Sim RTX). Input names from kit/mdl/core/Base/OmniSurface.mdl (Isaac Sim 6.2)."""
    shader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("omni_surface"))
    shader.SetSourceAsset(Sdf.AssetPath("OmniSurface.mdl"), "mdl")
    shader.SetSourceAssetSubIdentifier("OmniSurface", "mdl")
    f, c, b = Sdf.ValueTypeNames.Float, Sdf.ValueTypeNames.Color3f, Sdf.ValueTypeNames.Bool
    kind = spec.get("kind")
    shader.CreateInput("diffuse_reflection_weight", f).Set(1.0)
    if spec.get("diffuse") and kind != "vertex_color":
        _mdl_asset(shader, "diffuse_reflection_color_image", spec["diffuse"], "sRGB")
    shader.CreateInput("diffuse_reflection_color", c).Set(Gf.Vec3f(*map(float, spec.get("color") or (0.5, 0.5, 0.5))))
    shader.CreateInput("specular_reflection_roughness", f).Set(float(spec.get("roughness", 0.6)))
    if spec.get("roughness_map"):
        _mdl_asset(shader, "specular_reflection_roughness_image", spec["roughness_map"], "raw")
    if spec.get("normal"):
        _mdl_asset(shader, "geometry_normal_image", spec["normal"], "raw")
        shader.CreateInput("geometry_normal_strength", f).Set(1.0)
    if kind == "skin":
        shader.CreateInput("specular_reflection_ior", f).Set(1.4)
        sss = spec.get("subsurface") or {}
        if sss:
            radius = np.array(sss["radius_mm"], dtype=np.float64)
            shader.CreateInput("enable_diffuse_transmission", b).Set(True)
            shader.CreateInput("subsurface_weight", f).Set(float(sss["weight"]))
            if spec.get("diffuse"):
                _mdl_asset(shader, "subsurface_transmission_color_image", spec["diffuse"], "sRGB")
            shader.CreateInput("subsurface_transmission_color", c).Set(Gf.Vec3f(*map(float, spec.get("color"))))
            shader.CreateInput("subsurface_scattering_color", c).Set(Gf.Vec3f(*(radius / radius.max()).tolist()))
            shader.CreateInput("subsurface_scale", f).Set(float(radius.max() / 1000.0))        # mm -> m (scene units)
    elif kind == "cloth":
        shader.CreateInput("specular_reflection_weight", f).Set(0.35)
        shader.CreateInput("specular_retro_reflection_weight", f).Set(0.15)     # fabric fuzz / back scatter
        shader.CreateInput("specular_retro_reflection_roughness", f).Set(0.6)
    elif kind == "eye":
        shader.CreateInput("coat_weight", f).Set(1.0)                          # wet cornea
        shader.CreateInput("coat_roughness", f).Set(0.02)
    elif kind == "hair":
        shader.CreateInput("specular_reflection_anisotropy", f).Set(0.6)
    if spec.get("opacity_cutout") and spec.get("diffuse"):
        shader.CreateInput("enable_opacity", b).Set(True)
        _mdl_asset(shader, "geometry_opacity_image", spec["diffuse"], "sRGB")
        shader.CreateInput("geometry_opacity_threshold", f).Set(0.5)
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")


def define_material(stage, root_path, spec: dict, mdl: bool):
    path = root_path.AppendPath(f"_materials/{usd_name(spec['name'])}")
    existing = UsdShade.Material.Get(stage, path)
    if existing:
        return existing
    material = UsdShade.Material.Define(stage, path)
    _preview_surface(stage, material, spec)
    if mdl:
        _omni_surface(stage, material, spec)
    return material


# ---------------------------------------------------------------------------------------------- meshes
def _mesh(stage, path, points, faces, joint_index, joint_weight, skel, uv=None, uv_faces=None,
          double_sided=False, normals=True, face_colors=None):
    faces = [list(map(int, f)) for f in faces]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.asarray(points, dtype=np.float32)))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray([len(f) for f in faces]))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray([i for f in faces for i in f]))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(bool(double_sided))
    lo, hi = np.min(points, 0), np.max(points, 0)
    mesh.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*lo.tolist()), Gf.Vec3f(*hi.tolist())]))
    if normals:
        mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(vertex_normals(np.asarray(points), triangulate(faces))
                                                       .astype(np.float32)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    primvars = UsdGeom.PrimvarsAPI(mesh)
    if uv is not None and uv_faces is not None and len(uv) and all(len(t) == len(f) for t, f in zip(uv_faces, faces)):
        st = primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
        st.Set(Vt.Vec2fArray.FromNumpy(np.asarray(uv, dtype=np.float32)))
        st.SetIndices(Vt.IntArray([int(i) for t in uv_faces for i in t]))
    if face_colors is not None:
        primvars.CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.uniform).Set(
            Vt.Vec3fArray.FromNumpy(np.asarray(face_colors, dtype=np.float32)))
    binding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    k = joint_index.shape[1]
    binding.CreateJointIndicesPrimvar(False, k).Set(Vt.IntArray.FromNumpy(joint_index.reshape(-1).astype(np.int32)))
    binding.CreateJointWeightsPrimvar(False, k).Set(Vt.FloatArray.FromNumpy(joint_weight.reshape(-1).astype(np.float32)))
    binding.CreateGeomBindTransformAttr(Gf.Matrix4d(1.0))
    binding.CreateSkeletonRel().SetTargets([skel.GetPath()])
    return mesh


def write_human(path, human_id: str, joint_names, joint_parents, world, meshes: list, usd_cfg: dict,
                metadata: dict) -> dict:
    """joint_names / joint_parents / world: the full joint list (SkelOrigin first), world matrices [J, 4, 4].
    meshes: [{prim, mesh, points, faces, uv, uv_faces, joint_index, joint_weight, material, double_sided,
    face_colors, purpose}] with joint indices into joint_names."""
    world = np.asarray(world, dtype=np.float64)
    local = np.array([world[i] if p < 0 else np.linalg.inv(world[p]) @ world[i] for i, p in enumerate(joint_parents)])
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, float(usd_cfg.get("meters_per_unit", 1.0)))
    root_path = Sdf.Path(f"/{human_id}")
    human = UsdGeom.Xform.Define(stage, root_path)
    stage.SetDefaultPrim(human.GetPrim())
    human.GetPrim().SetCustomDataByKey("anny_human", metadata)
    human.GetPrim().SetKind("component")

    rig = UsdSkel.Root.Define(stage, root_path.AppendChild(f"{human_id}_rig"))
    skel = UsdSkel.Skeleton.Define(stage, rig.GetPath().AppendChild(f"{human_id}_rig"))
    skel.CreateJointsAttr(joint_paths(joint_names, joint_parents))
    skel.CreateJointNamesAttr(list(joint_names))
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray([_gf(m) for m in world]))
    skel.CreateRestTransformsAttr(Vt.Matrix4dArray([_gf(m) for m in local]))
    UsdSkel.BindingAPI.Apply(rig.GetPrim()).CreateSkeletonRel().SetTargets([skel.GetPath()])

    mdl = bool(usd_cfg.get("mdl", True))
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    written = []
    for item in meshes:
        xform = UsdGeom.Xform.Define(stage, rig.GetPath().AppendChild(usd_name(item["prim"])))
        mesh_path = xform.GetPath().AppendChild(usd_name(item["mesh"]))
        mesh = _mesh(stage, mesh_path, item["points"], item["faces"], np.asarray(item["joint_index"]),
                     np.asarray(item["joint_weight"]), skel, item.get("uv"), item.get("uv_faces"),
                     item.get("double_sided", False), bool(usd_cfg.get("normals", True)), item.get("face_colors"))
        if item.get("purpose"):
            mesh.CreatePurposeAttr().Set(item["purpose"])
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(define_material(stage, root_path, item["material"], mdl))
        written.append(str(mesh_path))
        if not item["prim"].startswith("bone_"):
            lo, hi = np.minimum(lo, np.min(item["points"], 0)), np.maximum(hi, np.max(item["points"], 0))
    stage.GetRootLayer().Save()
    _LOG.info(f"USD written: {path} ({len(written)} meshes, {len(joint_names)} joints)")
    return {"usd_skeleton_prim": str(skel.GetPath()), "meshes": written, "joint_count": len(joint_names),
            "bounds_m": [np.round(lo, 4).tolist(), np.round(hi, 4).tolist()]}
