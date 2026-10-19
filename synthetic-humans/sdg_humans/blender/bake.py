"""Cycles texture baking: turn any node material into a plain image-textured Principled BSDF.

The Blender USD exporter only converts Principled BSDF + image textures into
UsdPreviewSurface, so procedural MPFB materials are baked to PNG first.
"""

import logging
from pathlib import Path

import bpy

_LOG = logging.getLogger("sdg_humans.blender.bake")


def configure_cycles(device: str = "auto", samples: int = 4) -> str:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    used = "CPU"
    if device in ("auto", "GPU"):
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
                try:
                    prefs.compute_device_type = backend
                except TypeError:
                    continue
                prefs.get_devices()
                gpus = [d for d in prefs.devices if d.type != "CPU"]
                if gpus:
                    for d in prefs.devices:
                        d.use = d.type != "CPU"
                    scene.cycles.device = "GPU"
                    used = f"GPU ({backend})"
                    break
        except Exception as exc:  # noqa: BLE001 - any failure means CPU fallback
            _LOG.debug(f"GPU set-up failed, using CPU: {exc}")
    if used == "CPU":
        scene.cycles.device = "CPU"
        if device == "GPU":
            _LOG.warning("GPU bake requested but no GPU device is available; using CPU")
    _LOG.debug(f"Cycles bake device: {used}")
    return used


def _select_only(obj) -> None:
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def bake_diffuse_color(obj, image_path: Path, resolution: int, margin: int = 8) -> Path:
    """Bake the DIFFUSE colour of all materials on obj into one PNG (UV map must exist)."""
    image = bpy.data.images.new(f"{obj.name}_albedo", width=resolution, height=resolution, alpha=True)
    nodes = []
    for slot in obj.material_slots:
        if slot.material and slot.material.use_nodes:
            node = slot.material.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            slot.material.node_tree.nodes.active = node
            nodes.append((slot.material, node))
    _select_only(obj)
    bake = bpy.context.scene.render.bake
    bake.use_pass_direct = False
    bake.use_pass_indirect = False
    bake.use_pass_color = True
    bake.margin = margin
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True, margin=margin)
    image_path = Path(image_path)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image.filepath_raw = str(image_path)
    image.file_format = "PNG"
    image.save()
    for material, node in nodes:
        material.node_tree.nodes.remove(node)
    _LOG.info(f"baked {obj.name} albedo -> {image_path.name} ({resolution}px)")
    return image_path


def simple_material(name: str, image_path=None, color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, alpha_from_image=False):
    """Principled BSDF with an optional image texture (USD-exportable)."""
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Base Color"].default_value = color
    if image_path:
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(image_path), check_existing=True)
        tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha_from_image:
            tree.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return material


def replace_materials(obj, material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)
