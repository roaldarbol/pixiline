"""Small GUI preferences, persisted via ``QSettings``.

Pipeline parameters are no longer stored here - they live in each pipeline's
``pixi.toml`` (task ``args``) and are read via :mod:`raggui.manifest`. This module
only keeps cross-session GUI preferences that aren't pipeline parameters.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

_PARALLEL_KEY = "processing/parallel_enabled"
_OUTPUT_BASE_KEY = "io/output_base"
_RECENT_PIPELINES_KEY = "pipelines/recent"


def load_parallel_enabled() -> bool:
    return QSettings().value(_PARALLEL_KEY, False, type=bool)


def save_parallel_enabled(enabled: bool) -> None:
    QSettings().setValue(_PARALLEL_KEY, enabled)


def load_output_base() -> Path | None:
    """The last-used output base, or ``None`` if the user hasn't chosen one yet
    (there is no default - an output directory must always be chosen)."""
    stored = QSettings().value(_OUTPUT_BASE_KEY, "", type=str)
    return Path(stored) if stored else None


def save_output_base(path: Path) -> None:
    QSettings().setValue(_OUTPUT_BASE_KEY, str(path))


def load_recent_pipelines() -> list[Path]:
    """Pipeline directories opened in past sessions (most recent first)."""
    stored = QSettings().value(_RECENT_PIPELINES_KEY, [], type=list) or []
    return [Path(p) for p in stored if p]


def save_recent_pipelines(roots: list[Path]) -> None:
    QSettings().setValue(_RECENT_PIPELINES_KEY, [str(p) for p in roots])
