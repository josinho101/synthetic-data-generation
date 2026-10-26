from sdg_humans import preflight


def test_version_tuple():
    assert preflight._version_tuple("5.2.2 LTS") == (5, 2, 2)
    assert preflight._version_tuple("2.0.18") > preflight._version_tuple("2.0.9")


def test_missing_blender_is_error(cfg):
    cfg["export"]["blender_bin"] = "/nonexistent/blender"
    assert preflight.check_blender_binary(cfg).status == "error"


def test_unwritable_output_is_error(cfg, tmp_path):
    target = tmp_path / "ro"
    target.mkdir()
    target.chmod(0o500)
    cfg["export"]["output_root"] = str(target / "out")
    try:
        assert preflight.check_output(cfg).status == "error"
    finally:
        target.chmod(0o700)


def test_uncalibrated_anchors_are_error(cfg):
    cfg["landmarks"]["anchors"]["inion"] = None
    assert preflight.check_anchors(cfg).status == "error"


def test_report_returns_false_on_error():
    checks = [preflight.CheckResult("a", "ok", ""), preflight.CheckResult("b", "error", "boom")]
    assert preflight.report(checks) is False
