"""Well-known project paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
ISAAC_SCRIPT = PROJECT_ROOT / "isaac" / "run_exam.py"
COMPOSE_SCENE = REPO_ROOT / "room" / "isaac" / "compose_scene.py"

DEFAULT_HUMANS_ROOT = REPO_ROOT / "output" / "humans"
DEFAULT_ROOMS_ROOT = REPO_ROOT / "output" / "rooms"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "output" / "sdg"

CONFIG_FILES = ("run", "sequence", "poses", "isaac", "retarget_mpfb", "retarget_zanatomy", "capture", "annotations")
