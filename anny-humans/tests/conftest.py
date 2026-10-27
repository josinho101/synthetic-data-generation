import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anny_humans.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def base_cfg():
    return load_config(ROOT / "configs")


@pytest.fixture
def cfg(base_cfg):
    return copy.deepcopy(base_cfg)


@pytest.fixture(scope="session")
def catalogue():
    """Small synthetic target catalogue (keeps tests independent of the installed catalogue)."""
    def cat(name, sided=False):
        if sided:
            opp = {"negative-left": f"l-{name}-decr", "negative-right": f"r-{name}-decr",
                   "positive-left": f"l-{name}-incr", "positive-right": f"r-{name}-incr"}
        else:
            opp = {"negative-unsided": f"{name}-decr", "positive-unsided": f"{name}-incr"}
        return {"name": name, "has_left_and_right": sided, "opposites": opp, "targets": list(opp.values())}
    sections = ["nose", "chin", "eyes", "mouth", "ears", "cheek", "forehead", "head", "eyebrows", "neck"]
    return {s: [cat(f"{s}-a"), cat(f"{s}-b", sided=True), cat(f"{s}-c"), cat(f"{s}-d", sided=True)]
            for s in sections}


@pytest.fixture(scope="session")
def anny_body(base_cfg):
    """The Anny model (loaded once; the first load on a machine builds Anny's cache)."""
    pytest.importorskip("anny")
    from anny_humans.model import AnnyBody
    return AnnyBody(base_cfg["body"], "cpu")


@pytest.fixture(scope="session")
def built_human(base_cfg, anny_body, tmp_path_factory):
    """One human built end to end (sample -> build -> usd_post -> validate) into a temp run directory."""
    from anny_humans.pipeline.orchestrator import Builder, _build_one
    from anny_humans.run_context import create_run
    from anny_humans.sampling.manifest import build_specs
    cfg = copy.deepcopy(base_cfg)
    cfg["population"]["count"] = 2
    builder = Builder(cfg)
    builder._body = anny_body
    spec = build_specs(cfg, builder.catalogue)[0]
    ctx = create_run(tmp_path_factory.mktemp("run"))
    result = _build_one(builder, ctx, spec)
    return {"spec": spec, "result": result, "dir": ctx.human_dir(spec["id"]), "cfg": cfg}
