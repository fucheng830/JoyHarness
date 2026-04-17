"""Path utilities — works correctly both in development and when frozen by PyInstaller."""
import sys
from pathlib import Path


def get_app_root() -> Path:
    """Writable app root: EXE directory when frozen, project root in dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str) -> Path:
    """Read-only bundled resource (e.g. config/default.json)."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent.parent / relative_path
