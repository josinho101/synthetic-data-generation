"""Well-known project paths (stdlib only; importable inside Blender)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
ASSETS_DIR = PROJECT_ROOT / "assets"
CENTRAL_LOG_DIR = PROJECT_ROOT / "logs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

CONFIG_FILES = ("population", "appearance", "clothing", "garment_catalog", "gown", "landmarks", "anatomy", "skeleton",
                "export", "logging")
