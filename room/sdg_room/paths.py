"""Well-known project paths."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "configs"
CENTRAL_LOG_DIR = PROJECT_ROOT / "logs"

CONFIG_FILES = ("variations", "room", "equipment", "materials", "lighting", "props", "cameras", "export", "logging")
