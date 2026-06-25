"""A titled list 'card': a header bar attached to a list view, styled as one unit
(like a tab for the whole list). Used for the Pipelines and Inputs panels.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QListWidget, QVBoxLayout, QWidget

from pixiline.gui.theme import border_color, primary_surface, secondary_surface, watch_app_palette


class ListCard(QWidget):
    """A header strip + a borderless list, wrapped in one rounded, bordered card."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame()
        self._card.setObjectName("listCard")
        cv = QVBoxLayout(self._card)
        cv.setContentsMargins(1, 0, 1, 1)  # keep the list off the rounded border
        cv.setSpacing(0)

        self._header = QLabel(title)
        self._header.setObjectName("listCardHeader")
        cv.addWidget(self._header)

        self.list = QListWidget()
        self.list.setObjectName("listCardList")
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        cv.addWidget(self.list, 1)

        outer.addWidget(self._card)
        self._apply_theme()
        watch_app_palette(self, self._apply_theme)

    def _apply_theme(self) -> None:
        edge = border_color().name()
        prim = primary_surface().name()
        sec = secondary_surface().name()
        self._card.setStyleSheet(
            f"#listCard {{ border: 1px solid {edge}; border-radius: 6px; background: {prim}; }}"
        )
        self._header.setStyleSheet(
            "#listCardHeader {"
            f" background: {sec}; font-weight: bold; padding: 6px 10px;"
            f" border-bottom: 1px solid {edge};"
            " border-top-left-radius: 5px; border-top-right-radius: 5px; }"
        )
        self.list.setStyleSheet("#listCardList { background: transparent; border: none; }")
