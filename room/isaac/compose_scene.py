#!/usr/bin/env python3
"""Compose an Isaac Sim scene: a generated room + (optionally) a synthetic human standing on the floor marker.

Only `pxr` is needed (usd-core, or the Python that ships with Isaac Sim). Writes a small .usda that references
the room and the human, so the source files stay untouched:

    python isaac/compose_scene.py <run>/rooms/R0001/R0001.usd --out scene.usda
    python isaac/compose_scene.py <run>/rooms/R0001/R0001.usd \
        --human <humans run>/humans/H0001/H0001.usd --out scene_R0001_H0001.usda
    python isaac/compose_scene.py R0001.usd --human H0001_anim.usda --detector-height 1.35

Then in Isaac Sim: File -> Open the .usda (or drag it into an open stage as a reference) and press Play.

What it does:
  /World/Room     reference to the room USD (meters, Z-up; origin = interior floor corner at the entrance end)
  /World/Patient  reference to the human, placed at Room/Markers/PatientStand, facing the detector
                  (the synthetic humans face -Y, PatientStand's local -Y points at the detector)
  detector and tube heights are set to the human's T7 landmark height (PA chest centre) unless
  --detector-height is given; values are clamped to the travel limits stored on the room prims (sdg:travel_*).
"""

import argparse
import json
import sys
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

CARRIAGE = "Equipment/WallStand/Carriage"
ARM = "Equipment/TubeStand/Carriage/Arm"


def _chest_height(human_usd: Path):
    """T7 height (m) from the human's metadata JSON, or None."""
    stem = human_usd.stem.replace("_anim", "")
    meta = human_usd.with_name(f"{stem}.json")
    if not meta.exists():
        return None
    data = json.loads(meta.read_text())
    t7 = (data.get("landmarks") or {}).get("T7", {}).get("rest_position_m")
    if t7:
        return float(t7[2])
    cm = data.get("measurements_cm") or {}
    if "jugular_notch_height_cm" in cm and "xiphoid_height_cm" in cm:
        return (cm["jugular_notch_height_cm"] + cm["xiphoid_height_cm"]) / 200.0
    return None


def _clamp(prim, value):
    lo, hi = prim.GetAttribute("sdg:travel_min").Get(), prim.GetAttribute("sdg:travel_max").Get()
    return min(max(value, lo if lo is not None else value), hi if hi is not None else value)


def _set_translate_z(stage, path, z):
    prim = stage.GetPrimAtPath(path)
    op = next(o for o in UsdGeom.Xformable(prim).GetOrderedXformOps() if o.GetOpType() == UsdGeom.XformOp.TypeTranslate)
    t = op.Get()
    op.Set(Gf.Vec3d(t[0], t[1], z))


def compose(room_usd, out, human_usd=None, detector_height=None, room_prim="/World/Room"):
    room_usd, out = Path(room_usd).resolve(), Path(out).resolve()
    stage = Usd.Stage.CreateNew(str(out))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    room = stage.DefinePrim(room_prim, "Xform")
    room.GetReferences().AddReference(str(room_usd))

    stand = stage.GetPrimAtPath(f"{room_prim}/Markers/PatientStand")
    if not stand:
        raise SystemExit(f"{room_usd}: no Markers/PatientStand prim (not a generated room?)")
    m = UsdGeom.Xformable(stand).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    pos = m.ExtractTranslation()
    fwd = m.TransformDir(Gf.Vec3d(0, -1, 0))
    import math
    yaw = math.degrees(math.atan2(fwd[1], fwd[0])) + 90.0     # rotation that turns -Y onto `fwd`
    info = {"room": str(room_usd), "patient_stand": [round(v, 4) for v in pos], "patient_yaw_deg": round(yaw, 2)}

    height = detector_height
    if human_usd:
        human_usd = Path(human_usd).resolve()
        patient = UsdGeom.Xform.Define(stage, "/World/Patient")
        patient.AddTranslateOp().Set(Gf.Vec3d(pos[0], pos[1], 0.0))
        patient.AddRotateZOp().Set(float(yaw))
        patient.GetPrim().GetReferences().AddReference(str(human_usd))
        info["human"] = str(human_usd)
        if height is None:
            height = _chest_height(human_usd)
    if height is not None:
        carriage = stage.GetPrimAtPath(f"{room_prim}/{CARRIAGE}")
        arm = stage.GetPrimAtPath(f"{room_prim}/{ARM}")
        if carriage:
            h = _clamp(carriage, float(height))
            with Usd.EditContext(stage, stage.GetEditTarget()):
                _set_translate_z(stage, carriage.GetPath(), h)
                if arm:
                    _set_translate_z(stage, arm.GetPath(), _clamp(arm, h))
            info["detector_height_m"] = round(h, 4)
    stage.GetRootLayer().customLayerData = {"sdg_scene": json.dumps(info)}
    stage.GetRootLayer().Save()
    return info


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("room_usd")
    parser.add_argument("--human", help="synthetic human USD (H####.usd or H####_anim.usda)")
    parser.add_argument("--detector-height", type=float, help="detector/tube centre height in m (default: human T7)")
    parser.add_argument("--out", help="output .usda (default: scene_<room>[_<human>].usda next to the room)")
    args = parser.parse_args(argv)
    room = Path(args.room_usd)
    out = args.out or room.with_name(f"scene_{room.stem}" + (f"_{Path(args.human).stem}" if args.human else "") + ".usda")
    info = compose(room, out, args.human, args.detector_height)
    print(f"wrote {out}\n{json.dumps(info, indent=2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
