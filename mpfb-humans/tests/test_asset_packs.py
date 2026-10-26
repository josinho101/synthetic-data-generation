import zipfile

import pytest

from sdg_humans import asset_packs, preflight


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def packs_cfg(cfg, tmp_path):
    cfg["export"]["asset_packs_target"] = str(tmp_path / "mpfb_data")
    cfg["export"]["asset_packs"] = [{"name": "demo", "file": "demo_cc0.zip", "license": "CC0"}]
    return cfg


def test_missing_then_installed_from_dir(packs_cfg, tmp_path):
    zips = tmp_path / "zips"
    zips.mkdir()
    _zip(zips / "demo_cc0.zip", {"packs/demo.json": "{}", "hair/x/x.mhclo": "x", "evil.py": "print()"})
    assert [p["name"] for p in asset_packs.missing_packs(packs_cfg)] == ["demo"]
    results = asset_packs.install(packs_cfg, from_dir=zips)
    assert results[0]["status"] == "installed" and results[0]["files"] == 2
    target = tmp_path / "mpfb_data"
    assert (target / "hair/x/x.mhclo").exists() and not (target / "evil.py").exists()
    assert asset_packs.missing_packs(packs_cfg) == []
    assert asset_packs.install(packs_cfg, from_dir=zips)[0]["status"] == "skipped"


def test_unsafe_zip_is_rejected(packs_cfg, tmp_path):
    zips = tmp_path / "zips"
    zips.mkdir()
    _zip(zips / "demo_cc0.zip", {"../escape.png": "x"})
    assert asset_packs.install(packs_cfg, from_dir=zips)[0]["status"] == "failed"
    assert not (tmp_path / "escape.png").exists()


def test_preflight_pack_check(packs_cfg):
    assert preflight.check_asset_packs(packs_cfg).status == "warn"
    packs_cfg["export"]["asset_mode"] = "required"
    assert preflight.check_asset_packs(packs_cfg).status == "error"
