"""A VSCode-style activity bar: a narrow vertical strip of icon buttons that switch
the main area between top-level views (Pipelines, Jobs, ...).

Icons are wire-only (line art), painted in the theme colour; the active item gets a
left accent bar (not a filled background). Each item is ``(key, tooltip)``; selecting
one emits ``view_selected(key)``.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QVBoxLayout, QWidget

from raggui.gui.theme import border_color, is_dark, secondary_surface, watch_app_palette

_ACCENT = "#4a9eff"


def _wire_pen(color: QColor, width: float = 1.6) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_pipelines(p: QPainter, r: QRectF, color: QColor) -> None:
    """A tiny node graph (two inputs wired into one) — the pipeline/DAG motif."""
    p.setPen(_wire_pen(color))
    p.setBrush(Qt.BrushStyle.NoBrush)
    rad = r.width() * 0.11
    x0 = r.left() + r.width() * 0.26
    x1 = r.left() + r.width() * 0.74
    y0 = r.top() + r.height() * 0.26
    y1 = r.top() + r.height() * 0.74
    ym = r.center().y()
    p.drawLine(QPointF(x0, y0), QPointF(x1, ym))
    p.drawLine(QPointF(x0, y1), QPointF(x1, ym))
    for cx, cy in ((x0, y0), (x0, y1), (x1, ym)):
        p.drawEllipse(QPointF(cx, cy), rad, rad)


def _draw_jobs(p: QPainter, r: QRectF, color: QColor) -> None:
    """A small list/queue — bullets with lines."""
    p.setPen(_wire_pen(color))
    bx = r.left() + r.width() * 0.22
    x1 = r.left() + r.width() * 0.40
    x2 = r.right() - r.width() * 0.16
    for f in (0.30, 0.50, 0.70):
        y = r.top() + r.height() * f
        p.drawEllipse(QPointF(bx, y), 1.5, 1.5)
        p.drawLine(QPointF(x1, y), QPointF(x2, y))


_ICONS: dict[str, Callable[[QPainter, QRectF, QColor], None]] = {
    "pipelines": _draw_pipelines,
    "jobs": _draw_jobs,
}


class _ActivityButton(QAbstractButton):
    def __init__(self, key: str, tooltip: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._draw = _ICONS.get(key, _draw_jobs)
        self.setCheckable(True)
        self.setToolTip(tooltip)
        self.setFixedSize(46, 46)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return QSize(46, 46)

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        muted = QColor("#9aa0a6") if is_dark() else QColor("#7d838b")
        accent = QColor(_ACCENT)
        color = accent if on else muted

        if self.underMouse() and not on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 20) if is_dark() else QColor(0, 0, 0, 16))
            p.drawRoundedRect(self.rect().adjusted(3, 3, -3, -3), 6, 6)

        if on:  # left accent bar
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent)
            p.drawRoundedRect(
                QRectF(0.0, self.height() * 0.24, 3.0, self.height() * 0.52), 1.5, 1.5
            )

        self._draw(p, QRectF(self.rect()).adjusted(13, 13, -11, -13), color)
        p.end()


class ActivityBar(QWidget):
    view_selected = Signal(str)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(50)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        v = QVBoxLayout(self)
        v.setContentsMargins(2, 8, 2, 8)
        v.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, _ActivityButton] = {}

        for key, tip in items:
            btn = _ActivityButton(key, tip)
            btn.clicked.connect(lambda _=False, k=key: self.view_selected.emit(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            v.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        v.addStretch(1)

        self._apply_theme()
        watch_app_palette(self, self._on_theme)

    def select(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
            self.view_selected.emit(key)

    def _on_theme(self) -> None:
        self._apply_theme()
        for btn in self._buttons.values():
            btn.update()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"ActivityBar {{ background: {secondary_surface().name()}; "
            f"border-right: 1px solid {border_color().name()}; }}"
        )
