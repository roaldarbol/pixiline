"""Jobs tab — the queue manager: every queued recording, grouped by state, with a
live output log.

Rows are created from the shared :class:`JobQueue`'s ``job_added`` signal, so the
Inputs tab only has to ``submit`` jobs. Progress is measured in completed steps;
the status shows the step currently running. Clicking a row (or a job running)
shows its merged stdout/stderr in the log pane below.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from raggui.jobs.job import Job, JobState
from raggui.pipeline import step_by_name
from raggui.jobs.queue import JobQueue, suggested_worker_count

_FINISHED_STATES = frozenset({JobState.DONE, JobState.FAILED, JobState.CANCELED})

_GROUP_RUNNING = "Running"
_GROUP_PENDING = "Pending"
_GROUP_QUEUED = "Queued"
_GROUP_FINISHED = "Finished"
_GROUP_ORDER = (_GROUP_QUEUED, _GROUP_PENDING, _GROUP_RUNNING, _GROUP_FINISHED)


def _step_summary(job: Job) -> str:
    return f"{len(job.steps)} step{'s' if len(job.steps) != 1 else ''}"


class JobRow(QWidget):
    """A selectable job row: checkbox, name, step tag, progress, status, cancel."""

    cancel_clicked = Signal(int)
    focus_requested = Signal(int)

    def __init__(self, job: Job, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._job = job

        h = QHBoxLayout(self)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(8)

        self.select_check = QCheckBox()
        self.select_check.setToolTip("Select for 'Start selected' / 'Remove selected'")

        self.label = QLabel(job.label)
        self.label.setMinimumWidth(200)
        self.label.setToolTip(str(job.input_path))
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.tag = QLabel(_step_summary(job))
        self.tag.setFixedWidth(64)
        self.tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tag.setStyleSheet(
            "color: white; background: #4a9eff; border-radius: 6px; padding: 1px 6px;"
        )
        steps = step_by_name()
        self.tag.setToolTip(
            " → ".join(steps[s].label if s in steps else s for s in job.steps)
        )

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFormat("%p%")

        self.status = QLabel()
        self.status.setMinimumWidth(120)
        self.set_queued()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(72)
        self.cancel_btn.clicked.connect(lambda: self.cancel_clicked.emit(self._job.id))

        h.addWidget(self.select_check)
        h.addWidget(self.label)
        h.addWidget(self.tag)
        h.addWidget(self.bar, 1)
        h.addWidget(self.status)
        h.addWidget(self.cancel_btn)

    def job(self) -> Job:
        return self._job

    def is_checked(self) -> bool:
        return self.select_check.isChecked()

    def set_progress(self, fraction: float) -> None:
        self.bar.setValue(round(fraction * 1000))

    def _set_status(self, text: str, color: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")

    def set_queued(self) -> None:
        self._set_status("queued", "#888")

    def set_pending(self) -> None:
        self._set_status("pending", "#d0883a")

    def set_running_step(self, step_name: str) -> None:
        steps = step_by_name()
        title = steps[step_name].label if step_name in steps else step_name
        self._set_status(title, "#4a9eff")

    def set_done(self) -> None:
        self.bar.setValue(1000)
        self._set_status("done", "#4caf50")
        self.cancel_btn.setEnabled(False)

    def set_failed(self, message: str) -> None:
        self._set_status("failed", "#d04444")
        self.status.setToolTip(message)
        self.cancel_btn.setEnabled(False)

    def set_canceled(self) -> None:
        self._set_status("canceled", "#a06800")
        self.cancel_btn.setEnabled(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.focus_requested.emit(self._job.id)
        super().mousePressEvent(event)


class _JobGroup(QWidget):
    """A titled section holding the rows for one lifecycle state (hidden if empty)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = title
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self._header = QLabel(title)
        self._header.setStyleSheet("color: #aaa; font-weight: bold; padding: 8px 2px 2px 2px;")
        v.addWidget(self._header)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        v.addWidget(self._body)
        self.setVisible(False)

    def add_row(self, row: JobRow) -> None:
        self._body_layout.addWidget(row)
        row.show()

    def remove_row(self, row: JobRow) -> None:
        self._body_layout.removeWidget(row)

    def count(self) -> int:
        return self._body_layout.count()

    def refresh(self) -> None:
        n = self.count()
        self.setVisible(n > 0)
        self._header.setText(f"{self._title}  ({n})")


class JobsPanel(QWidget):
    """Lists every queued recording, grouped by state, with a live log pane."""

    parallel_toggled = Signal(bool)

    def __init__(self, queue: JobQueue, parallel_enabled: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._rows: dict[int, JobRow] = {}
        self._row_group: dict[int, str] = {}
        self._log_job_id: int | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Header controls.
        header = QHBoxLayout()
        self._start_all_btn = QPushButton("Start all")
        self._start_all_btn.clicked.connect(self._queue.start_all)
        self._start_sel_btn = QPushButton("Start selected")
        self._start_sel_btn.clicked.connect(self._start_selected)
        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn = QPushButton("Clear finished")
        self._clear_btn.clicked.connect(self.clear_finished)

        workers = suggested_worker_count()
        self._parallel_check = QCheckBox(f"Parallel (up to {workers})")
        self._parallel_check.setToolTip(
            "Run multiple recordings at once. The motion/predict steps are GPU-bound, "
            "so leave this off unless your machine can run several at once."
        )
        self._parallel_check.setEnabled(workers > 1)
        self._parallel_check.setChecked(parallel_enabled and workers > 1)
        self._parallel_check.toggled.connect(self.parallel_toggled)

        header.addWidget(self._start_all_btn)
        header.addWidget(self._start_sel_btn)
        header.addWidget(self._remove_btn)
        header.addWidget(self._clear_btn)
        header.addStretch(1)
        header.addWidget(self._parallel_check)
        outer.addLayout(header)

        # Split: job list (top) over log pane (bottom).
        split = QSplitter(Qt.Orientation.Vertical, self)

        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        self._empty = QLabel("No jobs yet. Add some from the Inputs tab.")
        self._empty.setStyleSheet("color: #888;")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        list_layout.addWidget(self._empty, 1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(0, 0, 0, 0)
        self._inner_layout.setSpacing(2)
        self._groups: dict[str, _JobGroup] = {}
        for title in _GROUP_ORDER:
            group = _JobGroup(title)
            self._groups[title] = group
            self._inner_layout.addWidget(group)
        self._inner_layout.addStretch(1)
        self._scroll.setWidget(self._inner)
        self._scroll.setVisible(False)
        list_layout.addWidget(self._scroll, 1)
        split.addWidget(list_container)

        # Log pane.
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_header = QLabel("Log")
        self._log_header.setStyleSheet("color: #aaa; font-weight: bold;")
        log_layout.addWidget(self._log_header)
        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(5000)
        self._log_view.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        log_layout.addWidget(self._log_view, 1)
        split.addWidget(log_container)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        outer.addWidget(split, 1)

        # Wire queue signals.
        queue.job_added.connect(self._on_added)
        queue.job_pending.connect(self._on_pending)
        queue.job_started.connect(self._on_started)
        queue.job_progress.connect(self._on_progress)
        queue.job_step.connect(self._on_step)
        queue.job_log.connect(self._on_log)
        queue.job_finished.connect(self._on_finished)
        queue.job_failed.connect(self._on_failed)
        queue.job_canceled.connect(self._on_canceled)
        queue.job_removed.connect(self._on_removed)
        self._update_buttons()

    # --- public API ---------------------------------------------------------

    def parallel_enabled(self) -> bool:
        return self._parallel_check.isChecked()

    def clear_finished(self) -> None:
        for job_id, row in list(self._rows.items()):
            if row.job().state in _FINISHED_STATES:
                self._queue.remove(job_id)
        self._update_buttons()

    # --- queue signal handlers ----------------------------------------------

    def _on_added(self, job_id: int) -> None:
        job = self._queue.get(job_id)
        if job is None or job_id in self._rows:
            return
        row = JobRow(job)
        row.cancel_clicked.connect(self._queue.cancel)
        row.focus_requested.connect(self._show_log_for)
        row.select_check.toggled.connect(self._update_buttons)
        self._rows[job_id] = row
        self._place_row(job_id, _GROUP_QUEUED)
        self._update_buttons()

    def _on_pending(self, job_id: int) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_pending()
            self._place_row(job_id, _GROUP_PENDING)
        self._update_buttons()

    def _on_started(self, job_id: int) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_running_step(row.job().current_step_name() or "")
            self._place_row(job_id, _GROUP_RUNNING)
        self._show_log_for(job_id)
        self._update_buttons()

    def _on_progress(self, job_id: int, fraction: float) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_progress(fraction)

    def _on_step(self, job_id: int, _index: int, step_name: str) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_running_step(step_name)

    def _on_log(self, job_id: int, text: str) -> None:
        if job_id != self._log_job_id:
            self._show_log_for(job_id)
            return
        self._log_view.appendPlainText(text.rstrip("\n"))

    def _on_finished(self, job_id: int) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_done()
            self._place_row(job_id, _GROUP_FINISHED)
        self._update_buttons()

    def _on_failed(self, job_id: int, message: str) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_failed(message)
            self._place_row(job_id, _GROUP_FINISHED)
        self._update_buttons()

    def _on_canceled(self, job_id: int) -> None:
        row = self._rows.get(job_id)
        if row is not None:
            row.set_canceled()
            self._place_row(job_id, _GROUP_FINISHED)
        self._update_buttons()

    def _on_removed(self, job_id: int) -> None:
        row = self._rows.pop(job_id, None)
        group = self._row_group.pop(job_id, None)
        if row is not None:
            if group is not None:
                self._groups[group].remove_row(row)
            row.setParent(None)
            row.deleteLater()
        if job_id == self._log_job_id:
            self._log_job_id = None
            self._log_view.clear()
            self._log_header.setText("Log")
        self._refresh_groups()
        self._update_buttons()

    # --- internals ----------------------------------------------------------

    def _show_log_for(self, job_id: int) -> None:
        job = self._queue.get(job_id)
        if job is None:
            return
        self._log_job_id = job_id
        self._log_header.setText(f"Log — {job.label}")
        self._log_view.setPlainText(job.log)
        self._log_view.moveCursor(self._log_view.textCursor().MoveOperation.End)

    def _place_row(self, job_id: int, target: str) -> None:
        row = self._rows.get(job_id)
        if row is None:
            return
        current = self._row_group.get(job_id)
        if current != target:
            if current is not None:
                self._groups[current].remove_row(row)
            self._groups[target].add_row(row)
            self._row_group[job_id] = target
        self._refresh_groups()

    def _refresh_groups(self) -> None:
        for group in self._groups.values():
            group.refresh()
        has_rows = bool(self._rows)
        self._empty.setVisible(not has_rows)
        self._scroll.setVisible(has_rows)

    def _checked_rows(self) -> list[JobRow]:
        return [row for row in self._rows.values() if row.is_checked()]

    def _start_selected(self) -> None:
        ids = [r.job().id for r in self._checked_rows() if r.job().state == JobState.QUEUED]
        if ids:
            self._queue.start(ids)

    def _remove_selected(self) -> None:
        for row in self._checked_rows():
            if row.job().state != JobState.RUNNING:
                self._queue.remove(row.job().id)
        self._update_buttons()

    def _update_buttons(self) -> None:
        jobs = [row.job() for row in self._rows.values()]
        has_staged = any(j.state == JobState.QUEUED for j in jobs)
        checked = self._checked_rows()
        self._start_all_btn.setEnabled(has_staged)
        self._start_sel_btn.setEnabled(any(r.job().state == JobState.QUEUED for r in checked))
        self._remove_btn.setEnabled(any(r.job().state != JobState.RUNNING for r in checked))
        self._clear_btn.setEnabled(any(j.state in _FINISHED_STATES for j in jobs))
