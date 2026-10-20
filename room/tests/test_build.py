import json

from pxr import Usd, UsdGeom, UsdLux

from sdg_room.config import apply_overrides
from sdg_room.metadata.writer import write_room_metadata
from sdg_room.pipeline.validate import validate_usd
from sdg_room.sampling.manifest import build_room_spec
from sdg_room.usd.build import build_room_usd


def _build(cfg, tmp_path, index=0):
    spec = build_room_spec(cfg, index)
    build = build_room_usd(cfg, spec, tmp_path / spec["id"], "test")
    return spec, build


def test_room_usd_is_isaac_ready(cfg, tmp_path):
    spec, build = _build(cfg, tmp_path)
    res = validate_usd(build["usd"], spec["footprint_m"], spec["ceiling_height_m"], cameras=spec["cameras"])
    assert res["status"] == "ok", res
    stage = Usd.Stage.Open(build["usd"])
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert stage.GetDefaultPrim().GetPath().pathString == "/Room"
    lights = [p for p in stage.Traverse() if p.IsA(UsdLux.RectLight)]
    assert lights and all(UsdLux.RectLight(p).GetColorTemperatureAttr().Get() == spec["cct_k"] for p in lights)


def test_detector_height_matches_spec(cfg, tmp_path):
    spec, build = _build(cfg, tmp_path, 1)
    stage = Usd.Stage.Open(build["usd"])
    det = stage.GetPrimAtPath("/Room/Equipment/WallStand/Carriage/Detector/Housing")
    root = stage.GetPrimAtPath("/Room")
    box = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default"]).ComputeRelativeBound(det, root).ComputeAlignedRange()
    center = (box.GetMin() + box.GetMax()) / 2
    want = spec["layout"]["equipment"]["detector"]["center"]
    assert abs(center[0] - want[0]) < 1e-3 and abs(center[2] - want[2]) < 1e-3


def test_metadata_is_written(cfg, tmp_path):
    spec, build = _build(cfg, tmp_path, 2)
    meta = write_room_metadata(tmp_path / "m.json", spec, build, "run-test", "test")
    loaded = json.loads((tmp_path / "m.json").read_text())
    assert loaded["anchors"]["sid_m"] == meta["anchors"]["sid_m"]
    assert loaded["lighting"]["photometry"]["exam"]["target_lux"] == spec["lux_target"]


def test_asset_override_references_external_usd(cfg, tmp_path):
    part = tmp_path / "stand.usda"
    s = Usd.Stage.CreateNew(str(part))
    s.SetDefaultPrim(UsdGeom.Xform.Define(s, "/Stand").GetPrim())
    s.GetRootLayer().Save()
    c = apply_overrides(cfg, {"equipment.wall_stand.asset": str(part)})
    spec, build = _build(c, tmp_path / "x")
    stage = Usd.Stage.Open(build["usd"])
    assert stage.GetPrimAtPath("/Room/Equipment/WallStand").HasAuthoredReferences()
    assert validate_usd(build["usd"], spec["footprint_m"])["status"] != "failed"
