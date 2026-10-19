"""Turn MPFB / MakeHuman (MakeSkin) materials into USD-exportable Principled + diffuse image.

The diffuse image is found by following the link into the Principled BSDF "Base Color"
(pack materials also carry normal / specular maps). Optionally the image is tinted (hair,
eyebrows) and its alpha used as a cut-out (hair cards, lace).
"""

import logging
from pathlib import Path

import bpy

from . import bake, colors

_LOG = logging.getLogger("sdg_humans.blender.materials")


def _upstream_image(socket, depth=0):
    if depth > 8 or not socket.is_linked:
        return None
    node = socket.links[0].from_node
    if node.type == "TEX_IMAGE" and node.image is not None:
        return node.image
    for inp in node.inputs:
        if inp.is_linked:
            found = _upstream_image(inp, depth + 1)
            if found is not None:
                return found
    return None


def diffuse_image(material):
    if material is None or not material.use_nodes:
        return None
    bsdf = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    image = _upstream_image(bsdf.inputs["Base Color"]) if bsdf else None
    if image is None:  # fall back to an image that is not obviously a normal / specular map
        for node in material.node_tree.nodes:
            name = (node.image.name.lower() if node.type == "TEX_IMAGE" and node.image else "")
            if name and not any(k in name for k in ("norm", "spec", "bump", "rough", "_nm", "ao")):
                return node.image
    return image


def _write_image(image, target: Path, tint_hex=None) -> Path:
    import numpy as np
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)
    if pixels.shape[2] == 3:
        pixels = np.dstack([pixels, np.ones((h, w), dtype=np.float32)])
    if tint_hex:
        grey = pixels[..., :3].mean(axis=2, keepdims=True)
        lift = 0.35 + 0.65 * grey / max(float(grey.max()), 1e-6)       # keep strand detail
        pixels[..., :3] = np.clip(lift * np.array(colors.hex_to_srgb(tint_hex), dtype=np.float32), 0, 1)
    out = bpy.data.images.new(target.stem, width=w, height=h, alpha=True)
    out.pixels[:] = pixels.ravel()
    out.filepath_raw = str(target)
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)
    return target


def _copy_alpha(source_image, target: Path) -> None:
    """Put the source texture's alpha (resampled) into the baked PNG (cut-outs, lace)."""
    import numpy as np
    sw, sh = source_image.size
    src = np.array(source_image.pixels[:], dtype=np.float32).reshape(sh, sw, source_image.channels)
    if src.shape[2] < 4 or src[..., 3].min() > 0.99:
        return
    baked = bpy.data.images.load(str(target), check_existing=False)
    w, h = baked.size
    pixels = np.array(baked.pixels[:], dtype=np.float32).reshape(h, w, 4)
    rows = (np.arange(h) * sh // h).clip(0, sh - 1)
    cols = (np.arange(w) * sw // w).clip(0, sw - 1)
    pixels[..., 3] = src[rows][:, cols, 3]
    baked.pixels[:] = pixels.ravel()
    baked.filepath_raw = str(target)
    baked.save()
    bpy.data.images.remove(baked)


def recolor_neutral(path: Path, rgb, max_saturation=0.15, min_value=0.55) -> int:
    """Recolour light, unsaturated pixels of a texture (e.g. a shoe's built-in sock) to rgb (sRGB 0..1),
    keeping their shading. Returns the number of pixels changed; reloads the image if loaded."""
    import numpy as np
    image = bpy.data.images.load(str(path), check_existing=True)
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)
    rgb_in = pixels[..., :3]
    value = rgb_in.max(axis=2)
    saturation = (value - rgb_in.min(axis=2)) / np.maximum(value, 1e-6)
    mask = (value > min_value) & (saturation < max_saturation)
    if pixels.shape[2] == 4:
        mask &= pixels[..., 3] > 0.5
    shade = (value / max(float(np.percentile(value[mask], 90)) if mask.any() else 1.0, 1e-6)).clip(0.5, 1.1)
    target = np.array(rgb, dtype=np.float32)
    pixels[..., :3] = np.where(mask[..., None], (shade[..., None] * target).clip(0, 1), rgb_in)
    image.pixels[:] = pixels.ravel()
    image.filepath_raw = str(path)
    image.save()
    return int(mask.sum())


def recolor_garment(path: Path, rgb) -> None:
    """Give a garment texture a new colour (sRGB 0..1) while keeping its shading and detail:
    out = rgb x (luminance / bright luminance). Buttons / prints keep their relative brightness."""
    import numpy as np
    image = bpy.data.images.load(str(path), check_existing=True)
    w, h = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32).reshape(h, w, image.channels)
    lum = pixels[..., :3] @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    mask = lum > 0.01
    if pixels.shape[2] == 4:
        mask &= pixels[..., 3] > 0.5
    if not mask.any():
        return
    ref = max(float(np.percentile(lum[mask], 85)), 1e-3)
    shade = (lum / ref).clip(0.0, 1.15)[..., None]
    target = np.array(rgb, dtype=np.float32)
    pixels[..., :3] = np.where(mask[..., None], (shade * target).clip(0, 1), pixels[..., :3])
    image.pixels[:] = pixels.ravel()
    image.filepath_raw = str(path)
    image.save()


def normalise(obj, name: str, textures_dir: Path, alpha=False, tint_hex=None, roughness=0.6,
              bake_colour=False, max_resolution=1024) -> str:
    """Replace obj's material(s) by one exportable material. Returns the texture file name or ''.

    bake_colour: bake the material's final diffuse colour (MakeHuman garments often store a
    grey shading texture that is multiplied by diffuseColor; the raw texture would be dark)."""
    image = diffuse_image(obj.active_material)
    if bake_colour and obj.data.uv_layers:
        size = min(max(image.size) if image is not None and image.size[0] else max_resolution, max_resolution)
        target = bake.bake_diffuse_color(obj, textures_dir / f"{name}.png", int(size))
        if alpha and image is not None:
            _copy_alpha(image, target)
        material = bake.simple_material(name, image_path=target, roughness=roughness, alpha_from_image=alpha)
        texture = target.name
    elif image is not None and image.size[0] > 0:
        target = textures_dir / f"{name}.png"
        _write_image(image, target, tint_hex)
        material = bake.simple_material(name, image_path=target, roughness=roughness, alpha_from_image=alpha)
        texture = target.name
    else:
        color = colors.hex_to_linear_rgba(tint_hex) if tint_hex else tuple(obj.active_material.diffuse_color) \
            if obj.active_material else (0.5, 0.5, 0.5, 1.0)
        material = bake.simple_material(name, color=color, roughness=roughness)
        texture = ""
    if alpha:
        material["sdg_alpha_cutout"] = True
        if hasattr(material, "blend_method"):
            try:
                material.blend_method = "CLIP"
            except TypeError:
                pass
    bake.replace_materials(obj, material)
    _LOG.debug(f"material {name}: texture={texture or '-'} alpha={alpha} tint={tint_hex}")
    return texture
