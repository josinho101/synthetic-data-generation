"""Blender task 'probe': report versions, MPFB location and installed asset counts (preflight)."""

import bpy

from . import bootstrap


def _count(ns, subdir, kind="mhclo"):
    try:
        lister = ns.AssetService.list_mhmat_assets if kind == "mhmat" else ns.AssetService.list_mhclo_assets
        return len(lister(subdir))
    except Exception:  # noqa: BLE001
        return 0


def run(args: dict) -> dict:
    ns = bootstrap.mpfb(args.get("mpfb_module", "auto"))
    counts = {"skins": _count(ns, "skins", "mhmat"), "eyes": _count(ns, "eyes"), "eyebrows": _count(ns, "eyebrows"),
              "eyelashes": _count(ns, "eyelashes"), "hair": _count(ns, "hair"), "clothes": _count(ns, "clothes")}
    try:
        system_assets = bool(ns.AssetService.system_assets_pack_is_installed())
    except Exception:  # noqa: BLE001
        system_assets = False
    gpus = []
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            gpus += [f"{backend}:{d.name}" for d in prefs.devices if d.type != "CPU"]
    except Exception:  # noqa: BLE001
        pass
    return {"status": "ok", "blender_version": bpy.app.version_string, "python": __import__("sys").version.split()[0],
            "mpfb_module": ns.module_name, "mpfb_version": bootstrap.mpfb_version(ns),
            "mpfb_data_dir": ns.LocationService.get_mpfb_data(), "user_data_dir": ns.LocationService.get_user_data(),
            "asset_counts": counts, "system_assets_installed": system_assets, "gpu_devices": sorted(set(gpus))}
