"""Well-known project paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
CENTRAL_LOG_DIR = PROJECT_ROOT / "logs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
# custom MHCLO garments (office skirt) of the MPFB pipeline; relative clothing.yaml `asset:` paths resolve here
CUSTOM_ASSETS_DIR = REPO_ROOT / "mpfb-humans" / "assets"

CONFIG_FILES = ("population", "appearance", "clothing", "body", "landmarks", "anatomy", "export", "logging")
