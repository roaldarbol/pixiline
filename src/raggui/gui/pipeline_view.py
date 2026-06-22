"""One loaded pipeline's workbench: add inputs + pick steps (left), tune the
pipeline's settings (right), and queue jobs.

Built entirely from the pipeline model (:mod:`raggui.manifest`): the step
checkboxes are the pipeline's steps in dependency order, and the Settings panel is
generated from each step's tunable ``args`` (those with a default). Settings are
shared by every input of this pipeline; the run identity (stem/output/input) comes
per input.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from raggui.config import load_output_base, save_output_base
from raggui.gui.dag_view import DagView
from raggui.gui.status_flash import StatusFlash
from raggui.jobs.job import Job
from raggui.manifest import Pipeline, Step, step_inputs_met


def _pretty(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").strip().capitalize()


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _inputs_from_urls(urls) -> list[Path]:
    return [
        Path(u.toLocalFile()) for u in urls if u.isLocalFile() and Path(u.toLocalFile()).is_file()
    ]


class _InputPanel(QWidget):
    """Per-input controls: gated step checkboxes, output base, a DAG view, queue.

    A step is enabled only when its inputs are satisfiable — by the dropped file,
    by an artifact already on disk under the output base, or by another currently
    selected step's outputs. Deselecting a step cascades to anything that depended
    on it. The DAG below mirrors the selection (unselected steps greyed)."""

    queue_requested = Signal(object)  # self

    def __init__(self, pipeline: Pipeline, input_path: Path, output_base: Path | None) -> None:
        super().__init__()
        self._pipeline = pipeline
        self._input = input_path
        self._order = pipeline.order()
        self._checks: dict[str, QCheckBox] = {}
        self._selected: set[str] = set()
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel(f"<b>{input_path.name}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(title)
        path_lbl = QLabel(str(input_path))
        path_lbl.setStyleSheet("color: #888;")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(path_lbl)

        root.addWidget(_hline())
        heading = QLabel("<b>Steps to run</b>")
        heading.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(heading)

        for step in self._order:
            label = f"{step.label}  (optional)" if step.optional else step.label
            cb = QCheckBox(label)
            cb.setToolTip(self._tooltip(step))
            cb.toggled.connect(lambda checked, n=step.name: self._on_toggle(n, checked))
            self._checks[step.name] = cb
            root.addWidget(cb)
        if not pipeline.steps:
            warn = QLabel("This pipeline declares no steps (tasks with inputs/outputs).")
            warn.setStyleSheet("color: #d0883a;")
            root.addWidget(warn)

        self._status = QLabel()
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        root.addWidget(_hline())
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output base:"))
        self._out_edit = QLineEdit(str(output_base) if output_base else "")
        self._out_edit.setReadOnly(True)
        self._out_edit.setPlaceholderText("Choose an output directory…")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(self._out_edit, 1)
        out_row.addWidget(browse)
        root.addLayout(out_row)

        # Rendered DAG of the steps, mirroring the selection.
        self._dag = DagView(pipeline)
        if pipeline.steps:
            dag_heading = QLabel("Pipeline")
            dag_heading.setStyleSheet("color: #888; padding-top: 4px;")
            root.addWidget(dag_heading)
            root.addWidget(self._dag)

        root.addStretch(1)
        queue_row = QHBoxLayout()
        self._queue_btn = QPushButton("Add to Queue")
        self._queue_btn.clicked.connect(lambda: self.queue_requested.emit(self))
        self._flash = StatusFlash()
        queue_row.addStretch(1)
        queue_row.addWidget(self._flash)
        queue_row.addWidget(self._queue_btn)
        root.addLayout(queue_row)

        # Default: every required (non-optional) step, then drop any that aren't
        # actually satisfiable from this input + on-disk artifacts.
        self._selected = {s.name for s in self._order if not s.optional}
        self._recompute()

    def _tooltip(self, step: Step) -> str:
        tip = f"{step.name}  (env: {step.env})"
        if step.description:
            tip += f"\n{step.description}"
        return tip

    @property
    def input_path(self) -> Path:
        return self._input

    @property
    def stem(self) -> str:
        return self._input.stem

    def selected_steps(self) -> list[str]:
        return [s.name for s in self._order if s.name in self._selected]

    def output_base(self) -> Path | None:
        text = self._out_edit.text().strip()
        return Path(text) if text else None

    def confirm_added(self) -> None:
        self._flash.flash("Added to queue ✓")

    # --- gating --------------------------------------------------------------

    def _satisfiable(self, step: Step, others: set[str]) -> bool:
        produced = {o for n in others for o in self._pipeline.step(n).outputs}
        return step_inputs_met(
            step,
            has_input=True,
            output_base=self.output_base(),
            stem=self.stem,
            produced=produced,
        )

    def _on_toggle(self, name: str, checked: bool) -> None:
        if self._syncing:
            return
        step = self._pipeline.step(name)
        if step is None:
            return
        if checked:
            if self._satisfiable(step, self._selected - {name}):
                self._selected.add(name)
        else:
            self._selected.discard(name)
        self._recompute()

    def _recompute(self) -> None:
        # Cascade: drop any selected step whose inputs are no longer satisfiable.
        changed = True
        while changed:
            changed = False
            for step in self._order:
                if step.name in self._selected and not self._satisfiable(
                    step, self._selected - {step.name}
                ):
                    self._selected.discard(step.name)
                    changed = True
        self._syncing = True
        for step in self._order:
            cb = self._checks[step.name]
            cb.setChecked(step.name in self._selected)
            cb.setEnabled(self._satisfiable(step, self._selected - {step.name}))
        self._syncing = False
        self._dag.set_selected(set(self._selected))
        self._update_status()

    def _update_status(self) -> None:
        if not self._pipeline.steps:
            return
        chain = [self._pipeline.step(n).label for n in self.selected_steps()]
        if chain:
            self._status.setText("Will run:  " + " → ".join(chain))
            self._status.setStyleSheet("color: #4caf50;")
        else:
            self._status.setText(
                "Pick a step to run — only steps whose inputs are available are enabled."
            )
            self._status.setStyleSheet("color: #d0883a;")

    def _browse_output(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output base", self._out_edit.text())
        if chosen:
            self._out_edit.setText(chosen)
            self._out_edit.setToolTip(chosen)
            save_output_base(Path(chosen))
            self._recompute()  # existing outputs may enable more steps


class _SettingsPanel(QWidget):
    """Right-hand panel: the pipeline's tunable args, grouped by step. Edits write
    into the shared ``values`` dict in place."""

    def __init__(self, pipeline: Pipeline, values: dict[str, str]) -> None:
        super().__init__()
        self._values = values

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 16, 12, 12)
        root.setSpacing(8)
        intro = QLabel("<b>Settings</b> — applied to every input of this pipeline.")
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        any_settings = False
        for step in pipeline.order():
            sargs = step.setting_args
            if not sargs:
                continue
            any_settings = True
            box = QGroupBox(step.label)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for arg in sargs:
                widget = self._make_widget(arg.name, arg.default or "", arg.choices)
                label = QLabel(_pretty(arg.name))
                form.addRow(label, widget)
            outer.addWidget(box)
        if not any_settings:
            outer.addWidget(QLabel("This pipeline exposes no settings."))
        outer.addStretch(1)
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

    def _make_widget(self, name: str, default: str, choices: tuple[str, ...] | None) -> QWidget:
        current = self._values.get(name, default)
        if choices:
            w = QComboBox()
            w.addItems(list(choices))
            if current in choices:
                w.setCurrentText(current)
            w.currentTextChanged.connect(lambda t, n=name: self._values.__setitem__(n, t))
            return w
        edit = QLineEdit(current)
        edit.textChanged.connect(lambda t, n=name: self._values.__setitem__(n, t))
        return edit


class PipelineView(QWidget):
    """The workbench for one loaded pipeline."""

    def __init__(self, pipeline: Pipeline, queue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._queue = queue
        self._settings = pipeline.default_settings()
        self._panels: list[_InputPanel] = []
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Left: input list + per-input panels.
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selected)
        lv.addWidget(self._list, 1)
        add_btn = QPushButton("Add files…")
        add_btn.clicked.connect(self._browse_inputs)
        lv.addWidget(add_btn)
        row = QHBoxLayout()
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._remove_current)
        self._queue_all_btn = QPushButton("Add all to queue")
        self._queue_all_btn.setEnabled(False)
        self._queue_all_btn.clicked.connect(self._queue_all)
        row.addWidget(self._remove_btn)
        row.addWidget(self._queue_all_btn)
        lv.addLayout(row)

        # Center: stacked per-input panels (+ placeholder).
        center = QWidget()
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget()
        self._placeholder = QLabel(
            "Add one or more input files to run this pipeline on.\nDrag files here too."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet("color: #888;")
        self._stack.addWidget(self._placeholder)
        cv.addWidget(self._stack, 1)

        # Right: settings.
        self._settings_panel = _SettingsPanel(pipeline, self._settings)

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(self._settings_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([220, 620, 320])
        layout.addWidget(splitter)

    # --- public API ----------------------------------------------------------

    @property
    def pipeline(self) -> Pipeline:
        return self._pipeline

    def add_inputs(self, paths: list[Path]) -> None:
        first = len(self._panels)
        for path in paths:
            panel = _InputPanel(self._pipeline, path, load_output_base())
            panel.queue_requested.connect(self._queue_panel)
            self._stack.addWidget(panel)
            self._panels.append(panel)
            self._list.addItem(path.name)
        if self._panels:
            self._list.setCurrentRow(first if first < len(self._panels) else len(self._panels) - 1)
            self._queue_all_btn.setEnabled(True)

    # --- internals -----------------------------------------------------------

    def _browse_inputs(self) -> None:
        base = load_output_base()
        start = str(base.parent) if base else ""
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", start, "All files (*)")
        if files:
            self.add_inputs([Path(f) for f in files])

    def _on_selected(self, row: int) -> None:
        if 0 <= row < len(self._panels):
            self._stack.setCurrentWidget(self._panels[row])
            self._remove_btn.setEnabled(True)
        else:
            self._stack.setCurrentWidget(self._placeholder)
            self._remove_btn.setEnabled(False)

    def _remove_current(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._panels)):
            return
        panel = self._panels.pop(row)
        self._stack.removeWidget(panel)
        panel.deleteLater()
        self._list.takeItem(row)
        if not self._panels:
            self._stack.setCurrentWidget(self._placeholder)
            self._remove_btn.setEnabled(False)
            self._queue_all_btn.setEnabled(False)

    def _queue_panel(self, panel: _InputPanel) -> None:
        steps = panel.selected_steps()
        if not steps:
            QMessageBox.information(self, "Add to Queue", "Select at least one step to run.")
            return
        output_base = panel.output_base()
        if output_base is None:
            QMessageBox.information(self, "Add to Queue", "Choose an output directory first.")
            return
        job = Job(
            pipeline=self._pipeline,
            input_path=panel.input_path,
            output_base=output_base,
            steps=steps,
            settings=dict(self._settings),  # snapshot the current settings
        )
        self._queue.submit(job)
        panel.confirm_added()

    def _queue_all(self) -> None:
        for panel in self._panels:
            self._queue_panel(panel)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if _inputs_from_urls(event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        inputs = _inputs_from_urls(event.mimeData().urls())
        if inputs:
            self.add_inputs(inputs)
            event.acceptProposedAction()
