"""Top-level QMainWindow: a tabbed host (Inputs / Jobs / Settings) sharing one
job queue, with a bottom status strip."""

from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QTabWidget

from raggui.config import load_parallel_enabled, save_parallel_enabled
from raggui.gui.jobs_panel import JobsPanel
from raggui.paths import workspace_title
from raggui.jobs.queue import JobQueue, suggested_worker_count
from raggui.gui.inputs_tab import InputsTab
from raggui.gui.settings_tab import SettingsTab
from raggui.gui.status_strip import StatusStrip


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(workspace_title())
        self.resize(1200, 800)

        self._queue = JobQueue(parent=self)
        parallel = load_parallel_enabled()

        self.tabs = QTabWidget(self)
        self.inputs_tab = InputsTab(self._queue)
        self.jobs_panel = JobsPanel(self._queue, parallel_enabled=parallel)
        self.jobs_panel.parallel_toggled.connect(self._on_parallel_toggled)
        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.inputs_tab, "Inputs")
        self.tabs.addTab(self.jobs_panel, "Jobs")
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setCentralWidget(self.tabs)

        self._status_strip = StatusStrip(self._queue)
        self.statusBar().addPermanentWidget(self._status_strip, 1)

        self._apply_parallel(self.jobs_panel.parallel_enabled())

    # --- public API ---------------------------------------------------------

    def shutdown(self) -> None:
        """Cancel running jobs before the app exits (so no pixi/processing
        subprocesses are orphaned)."""
        self._queue.shutdown()

    # --- Qt overrides --------------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.shutdown()
        super().closeEvent(event)

    # --- internals ----------------------------------------------------------

    def _on_parallel_toggled(self, enabled: bool) -> None:
        save_parallel_enabled(enabled)
        self._apply_parallel(enabled)

    def _apply_parallel(self, enabled: bool) -> None:
        self._queue.set_max_workers(suggested_worker_count() if enabled else 1)
