"""Locating the ``pixi`` launcher.

pixiline no longer has a fixed pipeline root - a pipeline's location comes from the
``pixi.toml`` the user drops in (see :mod:`pixiline.manifest`). The only path we need
globally is the ``pixi`` executable used to query and run pipelines.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def pixi_executable() -> str:
    """Locate the ``pixi`` launcher: ``PIXI_EXE`` override, then PATH, then the
    conventional ``~/.pixi/bin`` install. Falls back to the bare name."""
    override = os.environ.get("PIXI_EXE")
    if override:
        return override
    found = shutil.which("pixi")
    if found:
        return found
    home = Path.home() / ".pixi" / "bin"
    for name in ("pixi.exe", "pixi"):
        candidate = home / name
        if candidate.is_file():
            return str(candidate)
    return "pixi"
