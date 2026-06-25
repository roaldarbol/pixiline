"""A titled 'card': a header strip attached to arbitrary content, styled as one
rounded, bordered unit. The non-list sibling of :class:`pixiline.gui.list_card`."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from pixiline.gui.theme import border_color, primary_surface, secondary_surface, watch_app_palette


class Card(QWidget):
    def __init__(self, title: str, body: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._card = QFrame()
        self._card.setObjectName("card")
        cv = QVBoxLayout(self._card)
        cv.setContentsMargins(1, 0, 1, 1)
        cv.setSpacing(0)

        self._header = QLabel(title)
        self._header.setObjectName("cardHeader")
        cv.addWidget(self._header)

        wrap = QWidget()
        wv = QVBoxLayout(wrap)
        wv.setContentsMargins(10, 8, 10, 10)
        wv.addWidget(body)
        cv.addWidget(wrap, 1)

        outer.addWidget(self._card)
        self._apply_theme()
        watch_app_palette(self, self._apply_theme)

    def _apply_theme(self) -> None:
        edge = border_color().name()
        prim = primary_surface().name()
        sec = secondary_surface().name()
        self._card.setStyleSheet(
            f"#card {{ border: 1px solid {edge}; border-radius: 6px; background: {prim}; }}"
        )
        self._header.setStyleSheet(
            "#cardHeader {"
            f" background: {sec}; font-weight: bold; padding: 6px 10px;"
            f" border-bottom: 1px solid {edge};"
            " border-top-left-radius: 5px; border-top-right-radius: 5px; }"
        )
