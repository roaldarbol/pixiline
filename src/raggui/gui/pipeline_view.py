"""One loaded pipeline's workbench.

The flow is: pick the pipeline, configure it once (destination, which steps to run
+ the DAG, and the settings), then add the input files to process with it. So the
configuration is pipeline-level (center column) and the inputs are a plain file
list (right column) queued as a batch.

There is no config-time gating: any steps can be selected. Whether a step actually
runs for a given file is decided at run time (Snakemake-style) — a step is skipped
if its inputs aren't available for that file, and Pixi's task caching skips steps
whose outputs are already up to date. See jobs.worker.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from raggui.config import load_output_base, save_output_base
from raggui.gui.card import Card
from raggui.gui.dag_view import DagView
from raggui.gui.list_card import ListCard
from raggui.gui.status_flash import StatusFlash
from raggui.jobs.job import Job
from raggui.manifest import Pipeline

_QUEUE_BTN_QSS = (
    "QPushButton { background: #3b82f6; color: white; border: none; border-radius: 6px;"
    " padding: 9px 12px; font-weight: 600; }"
    "QPushButton:hover { background: #2f74e0; }"
    "QPushButton:disabled { background: #9bb4dd; color: #eef2fb; }"
)


def _pretty(name: str) -> str:
    return name.replace("-", " ").replace("_", " ").strip().capitalize()


def _inputs_from_urls(urls) -> list[Path]:
    return [
        Path(u.toLocalFile()) for u in urls if u.isLocalFile() and Path(u.toLocalFile()).is_file()
    ]


class PipelineView(QWidget):
    """Configure a pipeline (destination / steps / settings) and queue input files."""

    def __init__(self, pipeline: Pipeline, queue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._queue = queue
        self._order = pipeline.order()
        self._settings = pipeline.default_settings()
        self._selected: set[str] = {s.name for s in self._order if not s.optional}
        self._checks: dict[str, QCheckBox] = {}
        self._syncing = False
        self._files: list[Path] = []
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Orientation.Horizontal, self)
        split.addWidget(self._build_center())
        split.addWidget(self._build_inputs())
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 0)
        split.setSizes([760, 300])
        layout.addWidget(split)

        self._refresh()
        self._update_queue_enabled()

    # --- center: configuration ----------------------------------------------

    def _build_center(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(10, 10, 6, 10)
        center = QSplitter(Qt.Orientation.Vertical)
        center.addWidget(Card("Destination", self._build_output()))
        center.addWidget(Card("Steps", self._build_steps()))
        center.addWidget(Card("Settings", self._build_settings()))
        center.setStretchFactor(0, 0)
        center.setStretchFactor(1, 0)
        center.setStretchFactor(2, 1)
        center.setSizes([86, 280, 360])
        v.addWidget(center)
        return wrap

    def _build_output(self) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        self._out_edit = QLineEdit(str(load_output_base() or ""))
        self._out_edit.setReadOnly(True)
        self._out_edit.setPlaceholderText("Choose an output directory…")
        self._out_edit.setToolTip(self._out_edit.text())
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        row.addWidget(self._out_edit, 1)
        row.addWidget(browse)
        return w

    def _build_steps(self) -> QWidget:
        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)
        for step in self._order:
            label = f"{step.label}  (optional)" if step.optional else step.label
            cb = QCheckBox(label)
            cb.toggled.connect(lambda checked, n=step.name: self._on_toggle(n, checked))
            self._checks[step.name] = cb
            lv.addWidget(cb)
            desc = step.description
            if step.optional:
                desc = desc.replace("[optional]", "").replace("[OPTIONAL]", "").strip()
            if desc:
                d = QLabel(desc)
                d.setWordWrap(True)
                d.setStyleSheet("color: #888; margin-left: 22px; padding-bottom: 4px;")
                lv.addWidget(d)
        if not self._pipeline.steps:
            warn = QLabel("This pipeline declares no steps (tasks with inputs/outputs).")
            warn.setStyleSheet("color: #d0883a;")
            lv.addWidget(warn)
        self._status = QLabel()
        self._status.setWordWrap(True)
        lv.addWidget(self._status)
        lv.addStretch(1)
        h.addWidget(left, 1)

        self._dag = DagView(self._pipeline)
        self._dag.step_clicked.connect(self._on_dag_click)
        h.addWidget(self._dag, 0, Qt.AlignmentFlag.AlignTop)
        return body

    def _build_settings(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        note = QLabel("Applied to every input of this pipeline.")
        note.setStyleSheet("color: #888;")
        outer.addWidget(note)
        any_settings = False
        for step in self._order:
            sargs = step.setting_args
            if not sargs:
                continue
            any_settings = True
            box = QGroupBox(step.label)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            for arg in sargs:
                form.addRow(QLabel(_pretty(arg.name)), self._setting_widget(arg))
            outer.addWidget(box)
        if not any_settings:
            outer.addWidget(QLabel("This pipeline exposes no settings."))
        outer.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _setting_widget(self, arg) -> QWidget:
        name = arg.name
        current = self._settings.get(name, arg.default or "")
        if arg.choices:
            combo = QComboBox()
            combo.addItems(list(arg.choices))
            if current in arg.choices:
                combo.setCurrentText(current)
            combo.currentTextChanged.connect(lambda t, n=name: self._settings.__setitem__(n, t))
            return combo
        edit = QLineEdit(current)
        edit.textChanged.connect(lambda t, n=name: self._settings.__setitem__(n, t))
        return edit

    # --- right: inputs -------------------------------------------------------

    def _build_inputs(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 10, 10, 10)
        card = ListCard("Inputs")
        self._files_list = card.list
        self._files_list.currentRowChanged.connect(lambda r: self._remove_btn.setEnabled(r >= 0))
        v.addWidget(card, 1)

        add_btn = QPushButton("Add files…")
        add_btn.clicked.connect(self._browse_inputs)
        v.addWidget(add_btn)
        self._remove_btn = QPushButton("Remove")
        self._remove_btn.setEnabled(False)
        self._remove_btn.clicked.connect(self._remove_current)
        v.addWidget(self._remove_btn)

        v.addStretch(1)  # pin the queue button to the bottom
        self._flash = StatusFlash()
        v.addWidget(self._flash)
        self._queue_btn = QPushButton("Add to Queue")
        self._queue_btn.setStyleSheet(_QUEUE_BTN_QSS)
        self._queue_btn.clicked.connect(self._queue_all)
        v.addWidget(self._queue_btn)
        return w

    def add_inputs(self, paths: list[Path]) -> None:
        for path in paths:
            self._files.append(path)
            self._files_list.addItem(path.name)
        if self._files:
            self._files_list.setCurrentRow(len(self._files) - 1)
        self._update_queue_enabled()

    def _browse_inputs(self) -> None:
        base = self.output_base() or load_output_base()
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", str(base or ""), "All files (*)")
        if files:
            self.add_inputs([Path(f) for f in files])

    def _remove_current(self) -> None:
        row = self._files_list.currentRow()
        if 0 <= row < len(self._files):
            self._files.pop(row)
            self._files_list.takeItem(row)
            self._update_queue_enabled()

    def _queue_all(self) -> None:
        output_base = self.output_base()
        steps = self.selected_steps()
        if not (self._files and steps and output_base):
            return
        for path in self._files:
            self._queue.submit(
                Job(
                    pipeline=self._pipeline,
                    input_path=path,
                    output_base=output_base,
                    steps=steps,
                    settings=dict(self._settings),
                )
            )
        n = len(self._files)
        self._flash.flash(f"Added {n} file{'s' if n != 1 else ''} to queue ✓")

    # --- destination ---------------------------------------------------------

    def output_base(self) -> Path | None:
        text = self._out_edit.text().strip()
        return Path(text) if text else None

    def _browse_output(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose destination", self._out_edit.text())
        if chosen:
            self._out_edit.setText(chosen)
            self._out_edit.setToolTip(chosen)
            save_output_base(Path(chosen))
            self._update_queue_enabled()

    # --- steps (free selection; run-time decides what actually runs) ---------

    def selected_steps(self) -> list[str]:
        return [s.name for s in self._order if s.name in self._selected]

    def _on_toggle(self, name: str, checked: bool) -> None:
        if self._syncing:
            return
        if checked:
            self._selected.add(name)
        else:
            self._selected.discard(name)
        self._refresh()

    def _on_dag_click(self, name: str) -> None:
        if name in self._selected:
            self._selected.discard(name)
        else:
            self._selected.add(name)
        self._refresh()

    def _refresh(self) -> None:
        self._syncing = True
        for step in self._order:
            self._checks[step.name].setChecked(step.name in self._selected)
        self._syncing = False
        self._dag.set_selected(set(self._selected))
        self._update_status()
        self._update_queue_enabled()

    def _update_status(self) -> None:
        if not self._pipeline.steps:
            return
        chain = [self._pipeline.step(n).label for n in self.selected_steps()]
        if chain:
            self._status.setText(
                "Will run:  "
                + " → ".join(chain)
                + "   (steps whose inputs aren't ready are skipped per file)"
            )
            self._status.setStyleSheet("color: #4caf50;")
        else:
            self._status.setText("Pick at least one step to run.")
            self._status.setStyleSheet("color: #d0883a;")

    def _update_queue_enabled(self) -> None:
        missing = []
        if self.output_base() is None:
            missing.append("a destination")
        if not self._selected:
            missing.append("a step")
        if not self._files:
            missing.append("input files")
        self._queue_btn.setEnabled(not missing)
        self._queue_btn.setToolTip(
            "" if not missing else "Choose " + ", ".join(missing) + " first."
        )

    # --- drag & drop ---------------------------------------------------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if _inputs_from_urls(event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        inputs = _inputs_from_urls(event.mimeData().urls())
        if inputs:
            self.add_inputs(inputs)
            event.acceptProposedAction()
