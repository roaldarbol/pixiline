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
    """A workflow / flowchart: two boxes merging into one (icons8 'workflow' motif)."""
    p.setPen(_wire_pen(color, 1.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    bw = r.width() * 0.42
    bh = r.height() * 0.30
    lt = QRectF(r.left(), r.top(), bw, bh)
    lb = QRectF(r.left(), r.bottom() - bh, bw, bh)
    rm = QRectF(r.right() - bw, r.center().y() - bh / 2, bw, bh)
    midx = (lt.right() + rm.left()) / 2
    for box in (lt, lb):  # elbow connectors into the right box
        y = box.center().y()
        p.drawLine(QPointF(box.right(), y), QPointF(midx, y))
        p.drawLine(QPointF(midx, y), QPointF(midx, rm.center().y()))
    p.drawLine(QPointF(midx, rm.center().y()), QPointF(rm.left(), rm.center().y()))
    for box in (lt, lb, rm):
        p.drawRoundedRect(box, 2.5, 2.5)


def _draw_jobs(p: QPainter, r: QRectF, color: QColor) -> None:
    """A checklist: ticks beside lines (fontawesome 'list-check' motif)."""
    p.setPen(_wire_pen(color, 1.7))
    cx = r.left() + r.width() * 0.08
    s = r.height() * 0.11
    x_line0 = r.left() + r.width() * 0.44
    x_line1 = r.right() - r.width() * 0.04
    for f in (0.20, 0.5, 0.80):
        y = r.top() + r.height() * f
        p.drawLine(QPointF(cx, y), QPointF(cx + s, y + s))
        p.drawLine(QPointF(cx + s, y + s), QPointF(cx + s * 2.3, y - s * 1.4))
        p.drawLine(QPointF(x_line0, y), QPointF(x_line1, y))


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
