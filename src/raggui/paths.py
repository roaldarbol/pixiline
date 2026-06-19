"""Filesystem layout + workspace metadata, resolved relative to this package.

The GUI lives at ``<root>/src/gui/``; everything it drives (``pixi.toml``,
``config.yaml``) sits at the workspace root three levels up. Resolving from
``__file__`` means it works regardless of the launch cwd.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

#: Workspace root — parent of ``src/`` (this file is src/gui/paths.py).
PIPELINE_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PIPELINE_ROOT / "config.yaml"
PIXI_MANIFEST = PIPELINE_ROOT / "pixi.toml"

#: Fallback file globs for the "Add inputs" dialog when the pipeline declares no
#: external-input pattern (see pipeline.accepted_input_globs). "*" = accept anything.
FALLBACK_INPUT_GLOBS = ("*",)


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


def workspace_title() -> str:
    """A display title derived from the pixi workspace name (e.g.
    ``portia-sleep-pipeline`` → ``Portia Sleep Pipeline``)."""
    name = None
    try:
        import tomllib  # stdlib, Python 3.11+

        with PIXI_MANIFEST.open("rb") as fh:
            data = tomllib.load(fh)
        table = data.get("workspace") or data.get("project") or {}
        name = table.get("name")
    except Exception:
        name = None
    if not name:
        return "Pixi Pipeline"
    return name.replace("-", " ").replace("_", " ").strip().title()
