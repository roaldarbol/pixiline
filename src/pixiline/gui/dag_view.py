"""A rendered DAG of a pipeline's steps - the primary way to pick steps.

Nodes are laid out left-to-right by dependency depth (longest path from a root);
edges come from matching one step's outputs to another's inputs. Each node carries:

* a **checkbox** (top-right) that activates/deactivates the step - this is how
  steps are selected;
* a **run-order number** (left) shown only while the step is selected, counting its
  position in the selected chain (so it matches the "Run order" line and renumbers
  as steps are toggled);
* the step **label**.

Clicking a node's body (anywhere but the checkbox) focuses it, so the workbench can
show its description. Selected steps are drawn in the accent colour, unselected ones
greyed; the focused step gets an accent ring.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from pixiline.gui.theme import is_dark, primary_surface, watch_app_palette
from pixiline.manifest import Pipeline

_NODE_W = 150
_NODE_H = 30
_HGAP = 40
_VGAP = 16
_MARGIN = 12
_CHECK = 15  # checkbox side
_NUM_W = 18  # left gutter reserved for the run-order number
_ACCENT = "#4a9eff"


class DagView(QWidget):
    """Paints the pipeline graph. Checkboxes toggle selection (``step_toggled``);
    clicking a node body focuses it (``step_clicked``). ``set_selected`` /
    ``set_focused`` recolour it."""

    step_clicked = Signal(str)  # node body clicked -> focus (show its description)
    step_toggled = Signal(str)  # checkbox clicked -> activate/deactivate the step

    def __init__(self, pipeline: Pipeline, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._order_names = [s.name for s in pipeline.order()]
        self._selected: set[str] = set()
        self._focused: str | None = None
        self._run_index: dict[str, int] = {}
        self._edges = pipeline.edges()
        self._pos, self._cols, self._rows = self._layout()
        width = _MARGIN * 2 + self._cols * (_NODE_W + _HGAP) - _HGAP if self._cols else 0
        height = _MARGIN * 2 + self._rows * (_NODE_H + _VGAP) - _VGAP if self._rows else 0
        self.setMinimumSize(max(width, 0), max(height, 0))
        self.setMouseTracking(True)
        watch_app_palette(self, self.update)

    def set_selected(self, names: set[str]) -> None:
        self._selected = set(names)
        # Run-order numbers: position within the selected chain, in pipeline order.
        self._run_index = {
            name: i + 1
            for i, name in enumerate(n for n in self._order_names if n in self._selected)
        }
        self.update()

    def set_focused(self, name: str | None) -> None:
        self._focused = name
        self.update()

    # --- interaction ---------------------------------------------------------

    def _node_at(self, pos) -> str | None:
        return next((name for name in self._pos if self._rect(name).contains(pos)), None)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        name = self._node_at(event.position())
        if name is None:
            return
        if self._check_rect(name).contains(event.position()):
            self.step_toggled.emit(name)
        else:
            self.step_clicked.emit(name)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        name = self._node_at(event.position())
        if name is not None:
            on_check = self._check_rect(name).contains(event.position())
            step = self._pipeline.step(name)
            self.setToolTip(
                ("Toggle this step" if on_check else (step.description if step else "")) or name
            )
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setToolTip("")
            self.unsetCursor()

    # --- layout --------------------------------------------------------------

    def _layout(self) -> tuple[dict[str, tuple[int, int]], int, int]:
        order = self._order_names
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

    def _check_rect(self, name: str) -> QRectF:
        box = self._rect(name)
        return QRectF(box.right() - _CHECK - 7, box.top() + 5, _CHECK, _CHECK)

    # --- painting ------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = self.palette().windowText().color()
        muted = QColor("#9aa0a6") if is_dark() else QColor("#b0b6bd")
        accent = QColor(_ACCENT)
        focus_fill = QColor(74, 158, 255, 30)
        fill_on = primary_surface()

        self._paint_edges(painter, accent, muted)
        for name in self._pos:
            self._paint_node(painter, name, fg, muted, accent, fill_on, focus_fill)
        painter.end()

    def _paint_edges(self, painter: QPainter, accent: QColor, muted: QColor) -> None:
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

    def _paint_node(
        self,
        painter: QPainter,
        name: str,
        fg: QColor,
        muted: QColor,
        accent: QColor,
        fill_on,
        focus_fill: QColor,
    ) -> None:
        rect = self._rect(name)
        on = name in self._selected
        focused = name == self._focused
        step = self._pipeline.step(name)
        label = step.label if step else name
        base_font = painter.font()

        # Box: accent border when selected or focused; a faint accent wash on focus.
        border = accent if (on or focused) else muted
        painter.setPen(QPen(border, 2.0 if focused else (1.6 if on else 1.0)))
        if on:
            painter.setBrush(fill_on)
        elif focused:
            painter.setBrush(focus_fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 6, 6)

        self._paint_checkbox(painter, name, on, accent, muted)

        # Run-order number (left gutter), only while selected.
        if on and name in self._run_index:
            num_font = QFont(painter.font())
            num_font.setBold(True)
            num_font.setPointSizeF(max(7.0, num_font.pointSizeF() - 1))
            painter.setFont(num_font)
            painter.setPen(accent)
            num_rect = QRectF(rect.left() + 8, rect.top(), _NUM_W, rect.height())
            painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, str(self._run_index[name]))
            painter.setFont(base_font)  # restore for the label

        # Label, between the number gutter and the checkbox.
        painter.setPen(fg if on else muted)
        label_rect = QRectF(
            rect.left() + 8 + _NUM_W,
            rect.top(),
            rect.width() - (8 + _NUM_W) - (_CHECK + 12),
            rect.height(),
        )
        metrics = QFontMetrics(painter.font())
        text = metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(label_rect.width()))
        align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        painter.drawText(label_rect, align, text)

    def _paint_checkbox(
        self, painter: QPainter, name: str, on: bool, accent: QColor, muted: QColor
    ) -> None:
        cb = self._check_rect(name)
        painter.setPen(QPen(accent if on else muted, 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(cb, 3, 3)
        if on:
            tick = QPolygonF(
                [
                    QPointF(cb.left() + 3, cb.center().y() + 1),
                    QPointF(cb.left() + cb.width() * 0.42, cb.bottom() - 3),
                    QPointF(cb.right() - 2.5, cb.top() + 3.5),
                ]
            )
            pen = QPen(accent, 2.0)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(tick)
