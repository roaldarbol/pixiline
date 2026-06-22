"""Shared GUI layout constants (ported from croppy)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

# Standard inner margin for the panels in each tab's splitter.
PANEL_MARGIN = 8

# Vertical space reserved at the very top of every panel for an optional title
# row. Panels that have a title draw it here; the others leave it empty.
# Reserving it everywhere means the content boxes — the list and the right-hand
# panel — start at the same Y and so line up across the columns.
PANEL_HEADER_HEIGHT = 30


def panel_header(title: str = "") -> QLabel:
    """A fixed-height header row that keeps panel content aligned across columns.

    Pass a ``title`` (rich text allowed) for panels that have one, or leave it
    empty to simply reserve the matching space. Use together with a top content
    margin of 0 on the panel layout (the header supplies the top inset).
    """
    label = QLabel(title)
    label.setFixedHeight(PANEL_HEADER_HEIGHT)
    label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
    return label
