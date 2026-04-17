"""Unified entry point — works for both development and PyInstaller packaging."""
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller: src package is already bundled, no path manipulation needed
    pass
else:
    # Development: add project root to sys.path so `src` is importable
    _project_root = str(Path(__file__).resolve().parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

from src.main import main

main()
