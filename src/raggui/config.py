"""Read/write ``config.yaml`` and persist small GUI preferences.

The Settings tab is built *dynamically* from whatever is in ``config.yaml`` — no
hard-coded field list. We round-trip the file with ruamel.yaml so its comments and
layout survive a Save, and surface each value's end-of-line comment as the field's
tooltip.

GUI-only preferences (the parallel toggle, the last-used output base) live in
``QSettings``, not in ``config.yaml`` — they are not pipeline parameters.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from raggui.paths import CONFIG_PATH

_yaml = YAML()
_yaml.preserve_quotes = True


# --- config.yaml round-trip --------------------------------------------------


def load_config() -> Any:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return _yaml.load(fh)


def save_config(doc: Any) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as fh:
        _yaml.dump(doc, fh)


def comment_for(node: Any, key: Any) -> str:
    """The end-of-line comment on ``node[key]`` (e.g. ``# higher = fewer``), cleaned
    to a one-line tooltip. Empty string if there is none."""
    try:
        tokens = node.ca.items.get(key)
    except AttributeError:
        return ""
    if not tokens:
        return ""
    for token in tokens:
        value = getattr(token, "value", None)
        if value:
            return value.lstrip("#").strip().splitlines()[0].strip()
    return ""


def is_section(value: Any) -> bool:
    """Whether a top-level value is a group of settings rather than a scalar."""
    return isinstance(value, (CommentedMap, dict))


# --- GUI-only preferences (QSettings) ---------------------------------------

_PARALLEL_KEY = "processing/parallel_enabled"
_OUTPUT_BASE_KEY = "io/output_base"


def load_parallel_enabled() -> bool:
    return QSettings().value(_PARALLEL_KEY, False, type=bool)


def save_parallel_enabled(enabled: bool) -> None:
    QSettings().setValue(_PARALLEL_KEY, enabled)


def load_output_base() -> Path | None:
    """The last-used output base, or ``None`` if the user hasn't chosen one yet
    (there is no default — an output directory must always be chosen)."""
    stored = QSettings().value(_OUTPUT_BASE_KEY, "", type=str)
    return Path(stored) if stored else None


def save_output_base(path: Path) -> None:
    QSettings().setValue(_OUTPUT_BASE_KEY, str(path))
