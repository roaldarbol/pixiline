"""Top-level window.

A VSCode-style activity bar (far left) switches between top-level views:
  * Pipelines — the loaded-pipelines list and, beside it, the active pipeline's
    workbench (Inputs + Settings), or a drop screen when none are loaded.
  * Jobs — the single, app-wide job queue/monitor shared by every pipeline.

raggui opens with no pipeline; dropping (or browsing to) a ``pixi.toml`` adds one.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from raggui.config import load_parallel_enabled, save_parallel_enabled
from raggui.gui.activity_bar import ActivityBar
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
        self._pipeline_views: list[PipelineView] = []  # parallel to _pipelines

        # --- Pipelines view: list (left) + workbench (drop screen / a pipeline) ---
        self._sidebar = PipelinesSidebar()
        self._sidebar.pipeline_chosen.connect(self._add_pipeline)
        self._sidebar.selected.connect(self._on_pipeline_selected)
        self._sidebar.remove_requested.connect(self._remove_pipeline)
        self._sidebar.renamed.connect(self._rename_pipeline)

        self._drop = DropScreen()
        self._drop.pipeline_chosen.connect(self._add_pipeline)
        self._workbench = QStackedWidget()
        self._workbench.addWidget(self._drop)  # shown while no pipeline is active

        pipelines_view = QWidget()
        pv = QHBoxLayout(pipelines_view)
        pv.setContentsMargins(0, 0, 0, 0)
        psplit = QSplitter(Qt.Orientation.Horizontal)
        psplit.addWidget(self._sidebar)
        psplit.addWidget(self._workbench)
        psplit.setStretchFactor(0, 0)
        psplit.setStretchFactor(1, 1)
        psplit.setSizes([240, 1000])
        pv.addWidget(psplit)

        # --- Jobs view: the single shared queue/monitor ---
        parallel = load_parallel_enabled()
        self._jobs_panel = JobsPanel(self._queue, parallel_enabled=parallel)
        self._jobs_panel.parallel_toggled.connect(self._on_parallel_toggled)

        self._views = QStackedWidget()
        self._views.addWidget(pipelines_view)  # 0
        self._views.addWidget(self._jobs_panel)  # 1

        # --- Activity bar (far left) switches the views ---
        self._activity = ActivityBar([("pipelines", "Pipelines"), ("jobs", "Jobs")])
        self._activity.view_selected.connect(self._on_view_selected)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._activity)
        h.addWidget(self._views, 1)
        self.setCentralWidget(central)

        self._status_strip = StatusStrip(self._queue)
        self.statusBar().addPermanentWidget(self._status_strip, 1)

        self._activity.select("pipelines")
        self._apply_parallel(self._jobs_panel.parallel_enabled())

    # --- public API ----------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel running jobs before the app exits (so no pixi/processing
        subprocesses are orphaned)."""
        self._queue.shutdown()

    # --- Qt overrides --------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.shutdown()
        super().closeEvent(event)

    # --- views ---------------------------------------------------------------

    def _on_view_selected(self, key: str) -> None:
        self._views.setCurrentIndex(1 if key == "jobs" else 0)

    # --- pipelines -----------------------------------------------------------

    def _add_pipeline(self, root: Path) -> None:
        self._activity.select("pipelines")
        try:
            pipeline = load_pipeline(root, pixi_executable())
        except Exception as exc:  # noqa: BLE001 — surface any load failure to the user
            QMessageBox.critical(
                self, "Add pipeline", f"Could not read a pipeline from:\n{root}\n\n{exc}"
            )
            return
        # The same pixi.toml can be loaded several times (different settings); give
        # duplicates a numbered name. Rename via double-click in the sidebar.
        name = self._unique_name(pipeline.name)
        view = PipelineView(pipeline, self._queue)
        view.display_name = name
        self._pipelines.append(pipeline)
        self._pipeline_views.append(view)
        self._workbench.addWidget(view)
        self._sidebar.add_pipeline(name)  # selects it → _on_pipeline_selected

    def _unique_name(self, base: str) -> str:
        existing = {v.display_name for v in self._pipeline_views}
        if base not in existing:
            return base
        n = 2
        while f"{base} ({n})" in existing:
            n += 1
        return f"{base} ({n})"

    def _rename_pipeline(self, row: int, name: str) -> None:
        if not (0 <= row < len(self._pipeline_views)):
            return
        view = self._pipeline_views[row]
        if name.strip():
            view.display_name = name.strip()
        else:
            self._sidebar.set_name(row, view.display_name)  # revert empty rename

    def _on_pipeline_selected(self, row: int) -> None:
        if 0 <= row < len(self._pipeline_views):
            self._workbench.setCurrentWidget(self._pipeline_views[row])
        else:
            self._workbench.setCurrentWidget(self._drop)

    def _remove_pipeline(self, row: int) -> None:
        if not (0 <= row < len(self._pipelines)):
            return
        self._pipelines.pop(row)
        view = self._pipeline_views.pop(row)
        self._workbench.removeWidget(view)
        view.deleteLater()
        self._sidebar.remove_pipeline(row)
        if not self._pipelines:
            self._workbench.setCurrentWidget(self._drop)

    # --- internals -----------------------------------------------------------

    def _on_parallel_toggled(self, enabled: bool) -> None:
        save_parallel_enabled(enabled)
        self._apply_parallel(enabled)

    def _apply_parallel(self, enabled: bool) -> None:
        self._queue.set_max_workers(suggested_worker_count() if enabled else 1)
