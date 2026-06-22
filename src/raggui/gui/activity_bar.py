"""A VSCode-style activity bar: a narrow vertical strip of icon buttons that
switch the main area between top-level views (Pipelines, Jobs, ...).

Each item is ``(key, glyph, tooltip)``; selecting one emits ``view_selected(key)``.
Glyphs are unicode for now (no icon assets needed); swap for real icons later.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QToolButton, QVBoxLayout, QWidget

from raggui.gui.theme import border_color, is_dark, secondary_surface, watch_app_palette


class ActivityBar(QWidget):
    view_selected = Signal(str)

    def __init__(self, items: list[tuple[str, str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(52)

        v = QVBoxLayout(self)
        v.setContentsMargins(4, 8, 4, 8)
        v.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}

        for key, glyph, tip in items:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFixedSize(44, 44)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _=False, k=key: self.view_selected.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            v.addWidget(btn)
        v.addStretch(1)

        self._apply_theme()
        watch_app_palette(self, self._apply_theme)

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
            self.view_selected.emit(key)

    def _apply_theme(self) -> None:
        bar = secondary_surface().name()
        edge = border_color().name()
        accent = "#4a9eff"
        hover = "#ffffff22" if is_dark() else "#00000011"
        self.setStyleSheet(
            f"ActivityBar {{ background: {bar}; border-right: 1px solid {edge}; }}"
            "QToolButton { font-size: 20px; border: none; border-radius: 6px; }"
            f"QToolButton:hover {{ background: {hover}; }}"
            f"QToolButton:checked {{ background: {accent}33; color: {accent}; }}"
        )
