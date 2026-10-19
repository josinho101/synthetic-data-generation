"""Blender start-up helpers: enable MPFB, import its services, clear the scene."""

import importlib
import logging
from types import SimpleNamespace

import addon_utils
import bpy

_LOG = logging.getLogger("sdg_humans.blender.bootstrap")
_MPFB = None


def find_mpfb_module_name(configured: str = "auto") -> str:
    if configured and configured != "auto":
        return configured
    for module in addon_utils.modules():
        name = module.__name__
        if name == "mpfb" or name.endswith(".mpfb"):
            return name
    raise RuntimeError("MPFB extension not found in Blender (install it from extensions.blender.org)")


def mpfb(configured_module: str = "auto") -> SimpleNamespace:
    """Enable MPFB once and return a namespace with the services the pipeline uses."""
    global _MPFB
    if _MPFB is not None:
        return _MPFB
    name = find_mpfb_module_name(configured_module)
    addon_utils.enable(name, default_set=True)
    services = importlib.import_module(f"{name}.services")
    props = importlib.import_module(f"{name}.entities.objectproperties")
    mhclo_mod = importlib.import_module(f"{name}.entities.clothes.mhclo")
    _MPFB = SimpleNamespace(
        module_name=name,
        module=importlib.import_module(name),
        HumanService=services.HumanService,
        TargetService=services.TargetService,
        ObjectService=services.ObjectService,
        ClothesService=services.ClothesService,
        AssetService=services.AssetService,
        LocationService=services.LocationService,
        MaterialService=services.MaterialService,
        RigService=services.RigService,
        ExportService=importlib.import_module(f"{name}.services.exportservice").ExportService,
        HumanObjectProperties=props.HumanObjectProperties,
        GeneralObjectProperties=props.GeneralObjectProperties,
        Mhclo=mhclo_mod.Mhclo,
    )
    _LOG.debug(f"MPFB loaded from module {name}")
    return _MPFB


def mpfb_version(ns: SimpleNamespace) -> str:
    info = getattr(ns.module, "bl_info", None) or {}
    if info.get("version"):
        return ".".join(str(v) for v in info["version"])
    import os
    import re
    manifest = os.path.join(os.path.dirname(ns.module.__file__), "blender_manifest.toml")
    with open(manifest, "r", encoding="utf-8") as handle:
        match = re.search(r'^version\s*=\s*"([^"]+)"', handle.read(), re.M)
    return match.group(1) if match else "unknown"


def clear_scene() -> None:
    """Remove every object and orphan data block so each human starts from nothing."""
    bpy.ops.object.mode_set(mode="OBJECT") if bpy.context.object and bpy.context.object.mode != "OBJECT" else None
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in (bpy.data.meshes, bpy.data.materials, bpy.data.armatures, bpy.data.images,
                       bpy.data.cameras, bpy.data.lights):
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
