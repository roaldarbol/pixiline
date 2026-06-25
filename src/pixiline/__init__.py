"""pixiline - a generic Pixi-pipeline manager GUI.

Point it at a pipeline's ``pixi.toml`` (whose ``[tasks]`` are the steps); pixiline
reads the steps, their inputs and tunable settings, and the dependency graph
between them, then queues and runs them via ``pixi`` with a live terminal. It
carries no pipeline dependencies of its own.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pixiline")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0"
