"""Orthographic shaded previews (front + left side) of a written human USD, with Pillow only.

Rendered from the final USD (after usd_post), so it shows exactly what Isaac Sim loads: hole faces hidden, guide
meshes (anatomy) skipped, per-face colour sampled from the bound UsdPreviewSurface (diffuse texture at the face's UV
centre, or diffuseColor / displayColor), alpha cut-outs respected. Painter's algorithm, two-sided Lambert shading.
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import textures

LIGHT = np.array([0.3, -0.6, 0.75])
LIGHT = LIGHT / np.linalg.norm(LIGHT)
SAMPLE_PX = 96          # textures are averaged down to this size before sampling (smooth per-face colours)


def _to_srgb(lin):
    lin = np.clip(np.asarray(lin, dtype=np.float64), 0, 1)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * lin ** (1 / 2.4) - 0.055)


def _surface(prim):
    """-> (UsdPreviewSurface shader or None) bound to the mesh."""
    from pxr import UsdShade
    material = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    if not material:
        return None
    for child in material.GetPrim().GetChildren():
        shader = UsdShade.Shader(child)
        if shader and shader.GetIdAttr().Get() == "UsdPreviewSurface":
            return shader
    return None


def _diffuse(shader, usd_dir: Path, cache: dict):
    """-> (texture [h, w, 4] or None, constant sRGB colour, uses displayColor)."""
    from pxr import UsdShade
    color, texture, display = np.array([0.6, 0.6, 0.6]), None, False
    if shader is None:
        return texture, color, display
    inp = shader.GetInput("diffuseColor")
    if inp.HasConnectedSource():
        source = UsdShade.Shader(inp.GetConnectedSource()[0].GetPrim())
        if source.GetIdAttr().Get() == "UsdUVTexture":
            path = (usd_dir / source.GetInput("file").Get().path).resolve()
            if path not in cache:
                img = textures.load_rgba(path)
                h, w = img.shape[:2]
                step = max(1, max(h, w) // SAMPLE_PX)
                cache[path] = img[:h - h % step, :w - w % step].reshape(h // step, step, w // step, step, 4).mean((1, 3))
            texture = cache[path]
        else:
            display = True
    elif inp.Get() is not None:
        color = _to_srgb(inp.Get())
    return texture, color, display


def _mesh_triangles(prim, usd_dir: Path, cache: dict):
    """-> (triangles [T, 3, 3], sRGB colours [T, 3]) of one visible mesh."""
    from pxr import UsdGeom
    mesh = UsdGeom.Mesh(prim)
    points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
    counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int64)
    indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
    holes = set(int(h) for h in (mesh.GetHoleIndicesAttr().Get() or []))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    texture, color, display = _diffuse(_surface(prim), usd_dir, cache)
    primvars = UsdGeom.PrimvarsAPI(prim)
    st = primvars.GetPrimvar("st")
    uv = uv_idx = None
    if texture is not None and st and st.HasValue():
        uv = np.asarray(st.Get(), dtype=np.float64)
        uv_idx = np.asarray(st.GetIndices(), dtype=np.int64) if st.IsIndexed() else np.arange(len(indices))
    face_colors = None
    if display:
        dc = primvars.GetPrimvar("displayColor")
        if dc and dc.HasValue():
            face_colors = _to_srgb(np.asarray(dc.Get()))
    tris, cols = [], []
    for f, (start, n) in enumerate(zip(starts, counts)):
        if f in holes:
            continue
        c = color
        if face_colors is not None and len(face_colors) == len(counts):
            c = face_colors[f]
        elif uv is not None:
            u, v = uv[uv_idx[start:start + n]].mean(0)
            h, w = texture.shape[:2]
            px = texture[int(np.clip((1 - v % 1.0) * h, 0, h - 1)), int(np.clip((u % 1.0) * w, 0, w - 1))]
            if px[3] < 0.5:
                continue
            c = px[:3]
        face = indices[start:start + n]
        for k in range(1, n - 1):
            tris.append(points[[face[0], face[k], face[k + 1]]])
            cols.append(c)
    return tris, cols


def _view(tris, colors, size: int, side: bool, background) -> Image.Image:
    """tris [T, 3, 3] (m, Z-up, facing -Y). Front view looks along +Y, side view (subject's left) along -X."""
    p = tris if not side else tris @ np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]], dtype=np.float64).T
    normal = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-12
    order = np.argsort(-p[:, :, 1].mean(1))                    # far to near
    p, normal, colors = p[order], normal[order], colors[order]
    shade = 0.3 + 0.7 * np.abs(normal @ LIGHT)
    flat = p.reshape(-1, 3)
    lo, hi = flat.min(0), flat.max(0)
    scale = 0.92 * size / max(hi[2] - lo[2], 1e-6)
    centre_x = (lo[0] + hi[0]) / 2
    image = Image.new("RGB", (int(size * 0.75), size), background)
    draw = ImageDraw.Draw(image)
    width = image.size[0]
    for t, s, c in zip(p, shade, colors):
        xy = [(width / 2 + (v[0] - centre_x) * scale, size * 0.96 - (v[2] - lo[2]) * scale) for v in t]
        draw.polygon(xy, fill=tuple(int(255 * min(1.0, ch * s)) for ch in c))
    return image


def render_usd(usd_path, png_path, resolution=(512, 768), background="#d9dde3", label: str = "") -> Path:
    """Write <id>.png (front | left side) from the human USD."""
    from pxr import Usd, UsdGeom
    usd_path = Path(usd_path)
    stage = Usd.Stage.Open(str(usd_path))
    cache, all_tris, all_cols = {}, [], []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        if UsdGeom.Imageable(prim).ComputePurpose() != UsdGeom.Tokens.default_:
            continue
        tris, cols = _mesh_triangles(prim, usd_path.parent, cache)
        all_tris += tris
        all_cols += cols
    tris, colors = np.asarray(all_tris), np.asarray(all_cols)
    bg = tuple(int(255 * c) for c in textures.hex_to_srgb(background))
    size = int(resolution[1])
    front, side = _view(tris, colors, size, False, bg), _view(tris, colors, size, True, bg)
    sheet = Image.new("RGB", (front.size[0] * 2, size), bg)
    sheet.paste(front, (0, 0))
    sheet.paste(side, (front.size[0], 0))
    if label:
        ImageDraw.Draw(sheet).text((8, 8), label, fill=(30, 30, 30))
    sheet.save(png_path)
    return Path(png_path)
