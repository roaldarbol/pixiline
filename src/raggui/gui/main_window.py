"""Top-level window: a Pipelines sidebar, the active pipeline's workbench, and a
shared Jobs tab.

raggui opens with no pipeline. Dropping (or browsing to) a ``pixi.toml`` adds a
pipeline; its Inputs + Settings are instantiated from that manifest. Several
pipelines can be loaded at once and jobs queued from each into the shared queue.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
)

from raggui.config import load_parallel_enabled, save_parallel_enabled
from raggui.gui.drop_screen import DropScreen
from raggui.gui.jobs_panel import JobsPanel
from raggui.gui.pipeline_view import PipelineView
from raggui.gui.pipelines_sidebar import PipelinesSidebar
from raggui.gui.status_strip import StatusStrip
from raggui.gui.theme import apply_app_theme, watch_app_palette
from raggui.jobs.queue import JobQueue, suggested_worker_count
from raggui.manifest import Pipeline, load_pipeline
from raggui.paths import pixi_executable


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("raggui")
        self.resize(1280, 820)

        apply_app_theme()
        watch_app_palette(self, apply_app_theme)

        self._queue = JobQueue(parent=self)
        self._pipelines: list[Pipeline] = []

        # Sidebar (left) | main area (drop screen until a pipeline is loaded).
        self._sidebar = PipelinesSidebar()
        self._sidebar.pipeline_chosen.connect(self._add_pipeline)
        self._sidebar.selected.connect(self._on_pipeline_selected)
        self._sidebar.remove_requested.connect(self._remove_pipeline)

        self._drop = DropScreen()
        self._drop.pipeline_chosen.connect(self._add_pipeline)

        self._pipe_stack = QStackedWidget()  # one PipelineView per pipeline
        parallel = load_parallel_enabled()
        self._jobs_panel = JobsPanel(self._queue, parallel_enabled=parallel)
        self._jobs_panel.parallel_toggled.connect(self._on_parallel_toggled)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._pipe_stack, "Pipeline")
        self._tabs.addTab(self._jobs_panel, "Jobs")

        self._main = QStackedWidget()
        self._main.addWidget(self._drop)  # index 0: empty state
        self._main.addWidget(self._tabs)  # index 1: working state

        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.addWidget(self._sidebar)
        split.addWidget(self._main)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 1040])
        self.setCentralWidget(split)

        self._status_strip = StatusStrip(self._queue)
        self.statusBar().addPermanentWidget(self._status_strip, 1)

        self._apply_parallel(self._jobs_panel.parallel_enabled())
        self._show_empty_if_needed()

    # --- public API ----------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel running jobs before the app exits (so no pixi/processing
        subprocesses are orphaned)."""
        self._queue.shutdown()

    # --- Qt overrides --------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.shutdown()
        super().closeEvent(event)

    # --- pipelines -----------------------------------------------------------

    def _add_pipeline(self, root: Path) -> None:
        if any(p.root == root for p in self._pipelines):
            # Already loaded — just focus it.
            self._sidebar.list.setCurrentRow(
                next(i for i, p in enumerate(self._pipelines) if p.root == root)
            )
            return
        try:
            pipeline = load_pipeline(root, pixi_executable())
        except Exception as exc:  # noqa: BLE001 — surface any load failure to the user
            QMessageBox.critical(
                self, "Add pipeline", f"Could not read a pipeline from:\n{root}\n\n{exc}"
            )
            return
        view = PipelineView(pipeline, self._queue)
        self._pipelines.append(pipeline)
        self._pipe_stack.addWidget(view)
        self._sidebar.add_pipeline(pipeline.name)  # also selects it
        self._main.setCurrentWidget(self._tabs)
        self._tabs.setCurrentWidget(self._pipe_stack)

    def _on_pipeline_selected(self, row: int) -> None:
        if 0 <= row < self._pipe_stack.count():
            self._pipe_stack.setCurrentIndex(row)
            self._main.setCurrentWidget(self._tabs)

    def _remove_pipeline(self, row: int) -> None:
        if not (0 <= row < len(self._pipelines)):
            return
        self._pipelines.pop(row)
        view = self._pipe_stack.widget(row)
        self._pipe_stack.removeWidget(view)
        view.deleteLater()
        self._sidebar.remove_pipeline(row)
        self._show_empty_if_needed()

    def _show_empty_if_needed(self) -> None:
        if not self._pipelines:
            self._main.setCurrentWidget(self._drop)

    # --- internals -----------------------------------------------------------

    def _on_parallel_toggled(self, enabled: bool) -> None:
        save_parallel_enabled(enabled)
        self._apply_parallel(enabled)

    def _apply_parallel(self, enabled: bool) -> None:
        self._queue.set_max_workers(suggested_worker_count() if enabled else 1)
