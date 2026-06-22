"""The leftmost panel: the list of loaded pipelines.

Each pipeline is added by dropping (or browsing to) a ``pixi.toml``. Selecting one
makes it the active pipeline whose Inputs/Settings show on the right; multiple can
be loaded at once and jobs queued from each.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from raggui.gui.constants import PANEL_MARGIN
from raggui.gui.drop_screen import _roots_from_urls
from raggui.gui.list_card import ListCard


class PipelinesSidebar(QWidget):
    """A list of loaded pipelines with add/remove, and pixi.toml drop support."""

    pipeline_chosen = Signal(object)  # Path (pipeline root) to add
    selected = Signal(int)  # row, or -1
    remove_requested = Signal(int)  # row

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        v = QVBoxLayout(self)
        v.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)

        card = ListCard("Pipelines")
        self.list = card.list
        self.list.currentRowChanged.connect(self.selected)
        v.addWidget(card, 1)

        self.add_btn = QPushButton("Add pipeline…")
        self.add_btn.clicked.connect(self._browse)
        v.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setEnabled(False)
        self.remove_btn.clicked.connect(self._remove_current)
        v.addWidget(self.remove_btn)

        self.list.currentRowChanged.connect(lambda r: self.remove_btn.setEnabled(r >= 0))

    # --- public API ----------------------------------------------------------

    def add_pipeline(self, name: str) -> None:
        self.list.addItem(name)
        self.list.setCurrentRow(self.list.count() - 1)

    def remove_pipeline(self, row: int) -> None:
        item = self.list.takeItem(row)
        if item is not None:
            del item

    def current_row(self) -> int:
        return self.list.currentRow()

    # --- internals -----------------------------------------------------------

    def _browse(self) -> None:
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog

        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select a pipeline's pixi.toml", "", "Pixi manifest (pixi.toml);;All files (*)"
        )
        if chosen:
            from raggui.gui.drop_screen import pipeline_root_from

            root = pipeline_root_from(Path(chosen))
            if root is not None:
                self.pipeline_chosen.emit(root)

    def _remove_current(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.remove_requested.emit(row)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if _roots_from_urls(event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        roots = _roots_from_urls(event.mimeData().urls())
        if roots:
            event.acceptProposedAction()
            for root in roots:
                self.pipeline_chosen.emit(root)
        else:
            event.ignore()
