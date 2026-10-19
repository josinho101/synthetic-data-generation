import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sdg_humans.config import load_config  # noqa: E402


@pytest.fixture(scope="session")
def base_cfg():
    return load_config(ROOT / "configs")


@pytest.fixture
def cfg(base_cfg):
    return copy.deepcopy(base_cfg)


@pytest.fixture(scope="session")
def catalogue():
    """Small synthetic target catalogue (keeps tests independent of an MPFB install)."""
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
