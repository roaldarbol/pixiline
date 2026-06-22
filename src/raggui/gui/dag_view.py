"""A small rendered DAG of a pipeline's steps.

Nodes are laid out left-to-right by dependency depth (longest path from a root);
edges come from matching one step's outputs to another's inputs. Selected steps are
drawn in the accent colour, unselected ones greyed. Steps that connect to nothing
are just standalone nodes in the first column.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from raggui.gui.theme import is_dark, primary_surface, watch_app_palette
from raggui.manifest import Pipeline

_NODE_W = 96
_NODE_H = 26
_HGAP = 34
_VGAP = 12
_MARGIN = 10
_ACCENT = "#4a9eff"


class DagView(QWidget):
    """Paints the pipeline graph; ``set_selected`` recolours it."""

    def __init__(self, pipeline: Pipeline, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._selected: set[str] = set()
        self._edges = pipeline.edges()
        self._pos, self._cols, self._rows = self._layout()
        width = _MARGIN * 2 + self._cols * (_NODE_W + _HGAP) - _HGAP if self._cols else 0
        height = _MARGIN * 2 + self._rows * (_NODE_H + _VGAP) - _VGAP if self._rows else 0
        self.setMinimumSize(max(width, 0), max(height, 0))
        watch_app_palette(self, self.update)

    def set_selected(self, names: set[str]) -> None:
        self._selected = set(names)
        self.update()

    # --- layout --------------------------------------------------------------

    def _layout(self) -> tuple[dict[str, tuple[int, int]], int, int]:
        order = [s.name for s in self._pipeline.order()]
        preds: dict[str, list[str]] = {n: [] for n in order}
        for a, b in self._edges:
            preds[b].append(a)
        depth: dict[str, int] = {}
        for n in order:  # topo order: predecessors already have a depth
            depth[n] = max((depth[p] for p in preds[n]), default=-1) + 1
        columns: dict[int, list[str]] = {}
        for n in order:
            columns.setdefault(depth[n], []).append(n)
        pos = {n: (d, r) for d, names in columns.items() for r, n in enumerate(names)}
        n_cols = (max(depth.values()) + 1) if depth else 0
        n_rows = max((len(v) for v in columns.values()), default=0)
        return pos, n_cols, n_rows

    def _rect(self, name: str) -> QRectF:
        col, row = self._pos[name]
        x = _MARGIN + col * (_NODE_W + _HGAP)
        y = _MARGIN + row * (_NODE_H + _VGAP)
        return QRectF(x, y, _NODE_W, _NODE_H)

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = self.palette().windowText().color()
        muted = QColor("#9aa0a6") if is_dark() else QColor("#b0b6bd")
        accent = QColor(_ACCENT)
        fill_on = primary_surface()

        # Edges first (under the nodes).
        for a, b in self._edges:
            if a not in self._pos or b not in self._pos:
                continue
            ra, rb = self._rect(a), self._rect(b)
            on = a in self._selected and b in self._selected
            pen = QPen(accent if on else muted, 1.6 if on else 1.2)
            if not on:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            x1, y1 = ra.right(), ra.center().y()
            x2, y2 = rb.left(), rb.center().y()
            path = QPainterPath()
            path.moveTo(x1, y1)
            mid = (x1 + x2) / 2
            path.cubicTo(mid, y1, mid, y2, x2, y2)
            painter.drawPath(path)

        # Nodes.
        for name in self._pos:
            rect = self._rect(name)
            on = name in self._selected
            step = self._pipeline.step(name)
            label = step.label if step else name
            painter.setPen(QPen(accent if on else muted, 1.6 if on else 1.0))
            painter.setBrush(fill_on if on else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(fg if on else muted)
            metrics = QFontMetrics(painter.font())
            text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(rect.width()) - 10)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
