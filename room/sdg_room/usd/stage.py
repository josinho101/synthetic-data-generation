"""USD authoring helpers: stage set-up, Xforms, box / cylinder meshes with UVs, materials, semantics, colliders."""

import math
import re

from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade, Vt

from ..sampling.distributions import hex_to_rgb

# (normal, 4 corners as sign triples, uv axes as (axis index, sign) pairs)
_FACES = [
    ((1, 0, 0), [(1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)], ((1, 1), (2, 1))),
    ((-1, 0, 0), [(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)], ((1, -1), (2, 1))),
    ((0, 1, 0), [(1, 1, -1), (-1, 1, -1), (-1, 1, 1), (1, 1, 1)], ((0, -1), (2, 1))),
    ((0, -1, 0), [(-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)], ((0, 1), (2, 1))),
    ((0, 0, 1), [(-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], ((0, 1), (1, 1))),
    ((0, 0, -1), [(-1, 1, -1), (1, 1, -1), (1, -1, -1), (-1, -1, -1)], ((0, 1), (1, -1))),
]
_FIT_UV = [(0, 0), (1, 0), (1, 1), (0, 1)]


def safe_name(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    return f"_{name}" if name[:1].isdigit() else name


def create_stage(path, root_prim="/Room", meters_per_unit=1.0, up_axis="Z"):
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageMetersPerUnit(stage, meters_per_unit)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z if up_axis.upper() == "Z" else UsdGeom.Tokens.y)
    root = UsdGeom.Xform.Define(stage, root_prim).GetPrim()
    stage.SetDefaultPrim(root)
    Usd.ModelAPI(root).SetKind(Kind.Tokens.assembly)
    return stage, root


def xform(stage, path, translate=(0, 0, 0), rotate=(0, 0, 0)):
    """Xform with translate + rotateXYZ ops (degrees). Returns the UsdGeom.Xform."""
    xf = UsdGeom.Xform.Define(stage, path)
    if any(abs(v) > 1e-12 for v in translate):
        xf.AddTranslateOp().Set(Gf.Vec3d(*[float(v) for v in translate]))
    if any(abs(v) > 1e-12 for v in rotate):
        xf.AddRotateXYZOp().Set(Gf.Vec3f(*[float(v) for v in rotate]))
    return xf


def set_custom(prim, name, value, type_name=None):
    """Custom attribute `sdg:<name>` (documents a value for downstream scripts)."""
    if type_name is None:
        type_name = (Sdf.ValueTypeNames.Bool if isinstance(value, bool) else
                     Sdf.ValueTypeNames.Double if isinstance(value, (int, float)) else
                     Sdf.ValueTypeNames.Double3 if isinstance(value, (list, tuple)) and len(value) == 3 else
                     Sdf.ValueTypeNames.String)
    if type_name == Sdf.ValueTypeNames.Double3:
        value = Gf.Vec3d(*[float(v) for v in value])
    attr = prim.CreateAttribute(f"sdg:{name}", type_name, custom=True)
    attr.Set(value)
    return attr


def add_semantics(prim, label: str) -> None:
    """Class label in both Isaac Sim formats: legacy Semantics schema and the newer UsdSemantics labels."""
    prim.AddAppliedSchema("SemanticsAPI:Semantics")
    prim.CreateAttribute("semantic:Semantics:params:semanticType", Sdf.ValueTypeNames.String).Set("class")
    prim.CreateAttribute("semantic:Semantics:params:semanticData", Sdf.ValueTypeNames.String).Set(label)
    prim.AddAppliedSchema("SemanticsLabelsAPI:class")
    prim.CreateAttribute("semantics:labels:class", Sdf.ValueTypeNames.TokenArray).Set(Vt.TokenArray([label]))


def add_collider(prim, approximation="convexHull") -> None:
    UsdPhysics.CollisionAPI.Apply(prim)
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr().Set(approximation)


def _finish_mesh(mesh, points, counts, indices, normals, uvs, extent):
    mesh.CreatePointsAttr(Vt.Vec3fArray([Gf.Vec3f(*p) for p in points]))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray(counts))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray(indices))
    mesh.CreateSubdivisionSchemeAttr().Set(UsdGeom.Tokens.none)
    # normals / uvs are given per point (every face owns its points) -> faceVarying in face-vertex order
    mesh.CreateNormalsAttr(Vt.Vec3fArray([Gf.Vec3f(*normals[i]) for i in indices]))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
    st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
    st.Set(Vt.Vec2fArray([Gf.Vec2f(*uvs[i]) for i in indices]))
    mesh.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*extent[0]), Gf.Vec3f(*extent[1])]))


def box_mesh(stage, path, size, center=(0, 0, 0), uv_size=1.0):
    """Axis-aligned box. uv_size: meters per texture repeat (UVs from object coordinates) or "fit" (0..1 per face)."""
    half = [s / 2.0 for s in size]
    points, normals, uvs, counts, indices = [], [], [], [], []
    for normal, corners, (ua, va) in _FACES:
        base = len(points)
        for k, c in enumerate(corners):
            p = tuple(center[i] + c[i] * half[i] for i in range(3))
            points.append(p)
            if uv_size == "fit":
                uvs.append(_FIT_UV[k])
            else:
                uvs.append((p[ua[0]] * ua[1] / uv_size, p[va[0]] * va[1] / uv_size))
        normals += [normal] * 4
        counts.append(4)
        indices += [base, base + 1, base + 2, base + 3]
    mesh = UsdGeom.Mesh.Define(stage, path)
    ext = ([center[i] - half[i] for i in range(3)], [center[i] + half[i] for i in range(3)])
    _finish_mesh(mesh, points, counts, indices, normals, uvs, ext)
    return mesh


def cylinder_mesh(stage, path, radius, length, axis="z", center=(0, 0, 0), segments=24):
    """Capped cylinder along `axis` (x / y / z)."""
    ax = "xyz".index(axis)
    o1, o2 = [i for i in range(3) if i != ax]

    def vec(a, r1, r2):
        v = [0.0, 0.0, 0.0]
        v[ax], v[o1], v[o2] = a, r1, r2
        return tuple(center[i] + v[i] for i in range(3))

    def nvec(a, r1, r2):
        v = [0.0, 0.0, 0.0]
        v[ax], v[o1], v[o2] = a, r1, r2
        return tuple(v)

    points, normals, uvs, counts, indices = [], [], [], [], []
    h = length / 2.0
    angles = [2 * math.pi * k / segments for k in range(segments + 1)]
    for k in range(segments):          # side quads (normals per face-vertex, smooth)
        a0, a1 = angles[k], angles[k + 1]
        base = len(points)
        for a, z in ((a0, -h), (a1, -h), (a1, h), (a0, h)):
            points.append(vec(z, radius * math.cos(a), radius * math.sin(a)))
            normals.append(nvec(0, math.cos(a), math.sin(a)))
            uvs.append((a * radius, z))
        counts.append(4)
        indices += [base, base + 1, base + 2, base + 3]
    for z, sign in ((h, 1), (-h, -1)):  # caps
        base = len(points)
        ring = angles[:-1] if sign > 0 else list(reversed(angles[:-1]))
        for a in ring:
            points.append(vec(z, radius * math.cos(a), radius * math.sin(a)))
            normals.append(nvec(sign, 0, 0))
            uvs.append((radius * math.cos(a), radius * math.sin(a)))
        counts.append(segments)
        indices += list(range(base, base + segments))
    # winding is outward when (o1, o2, axis) is right-handed (x and z axes); for the y axis flip every face
    if axis == "y":
        indices = _flip(indices, counts)
    mesh = UsdGeom.Mesh.Define(stage, path)
    lo = [center[i] - (h if i == ax else radius) for i in range(3)]
    hi = [center[i] + (h if i == ax else radius) for i in range(3)]
    _finish_mesh(mesh, points, counts, indices, normals, uvs, (lo, hi))
    return mesh


def _flip(indices, counts):
    out, pos = [], 0
    for c in counts:
        out += list(reversed(indices[pos:pos + c]))
        pos += c
    return out


class Looks:
    """UsdPreviewSurface materials under <root>/Looks, cached by name."""

    def __init__(self, stage, root_path):
        self.stage = stage
        self.scope = f"{root_path}/Looks"
        UsdGeom.Scope.Define(stage, self.scope)
        self.cache = {}

    def get(self, name):
        return self.cache.get(safe_name(name))

    def make(self, name, color="#cccccc", roughness=0.5, metallic=0.0, clearcoat=0.0, clearcoat_roughness=0.05,
             texture=None, opacity=1.0, opacity_from_texture=False, emissive=None, ior=1.5):
        name = safe_name(name)
        if name in self.cache:
            return self.cache[name]
        path = f"{self.scope}/{name}"
        mat = UsdShade.Material.Define(self.stage, path)
        shader = UsdShade.Shader.Define(self.stage, f"{path}/PreviewSurface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
        shader.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(float(clearcoat))
        shader.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(float(clearcoat_roughness))
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(float(ior))
        if emissive:
            shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*emissive))
        if texture:
            reader = UsdShade.Shader.Define(self.stage, f"{path}/StReader")
            reader.CreateIdAttr("UsdPrimvarReader_float2")
            reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
            tex = UsdShade.Shader.Define(self.stage, f"{path}/DiffuseTexture")
            tex.CreateIdAttr("UsdUVTexture")
            tex.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture)
            tex.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
            tex.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
            tex.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set("sRGB")
            tex.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
            rgb = tex.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(rgb)
            if opacity_from_texture:
                alpha = tex.CreateOutput("a", Sdf.ValueTypeNames.Float)
                shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(alpha)
                shader.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(0.5)
        else:
            shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*hex_to_rgb(color)))
        if not opacity_from_texture and opacity < 1.0:
            shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
        out = shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput().ConnectToSource(out)
        self.cache[name] = mat
        return mat

    def color(self, hex_color, roughness=0.5, metallic=0.0, clearcoat=0.0):
        """Plain coloured material, shared by every prim with the same finish."""
        key = f"C_{hex_color.lstrip('#')}_r{int(roughness * 100)}_m{int(metallic * 100)}_c{int(clearcoat * 100)}"
        return self.make(key, color=hex_color, roughness=roughness, metallic=metallic, clearcoat=clearcoat)


def bind(prim, material) -> None:
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)
