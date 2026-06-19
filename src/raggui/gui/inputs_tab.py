"""Inputs tab: add one or more input files, pick the steps to run for each, queue.

A left list of added inputs, a per-input panel on the right (which steps to run,
the output base, an overwrite flag). The app is pipeline-agnostic: the accepted
file types come from the pipeline's external-input patterns (config.yaml `steps:`),
not a hard-coded video list. Scientific parameters live in the Settings tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from raggui.config import load_output_base, save_output_base
from raggui.jobs.job import Job
from raggui.paths import FALLBACK_INPUT_GLOBS, workspace_title
from raggui.pipeline import accepted_input_globs, discover_steps, step_plan


def _globs() -> list[str]:
    """Accepted input globs from the pipeline, or the fallback (accept anything)."""
    found = accepted_input_globs()
    return found if found else list(FALLBACK_INPUT_GLOBS)


def _input_filter() -> str:
    globs = _globs()
    if globs == ["*"]:
        return "All files (*)"
    return f"Input files ({' '.join(globs)});;All files (*)"


def _input_suffixes() -> set[str]:
    """Lower-cased suffixes (".mp4", …) accepted from drops. Empty set = accept any
    file (e.g. the pipeline accepts ``*`` or a non-extension glob)."""
    suffixes: set[str] = set()
    for glob in _globs():
        if glob == "*":
            return set()
        if glob.startswith("*.") and len(glob) > 2:
            suffixes.add(glob[1:].lower())  # "*.mp4" -> ".mp4"
    return suffixes


def _inputs_from_urls(urls) -> list[Path]:
    paths = [Path(url.toLocalFile()) for url in urls if url.isLocalFile()]
    suffixes = _input_suffixes()
    if not suffixes:
        return paths
    return [p for p in paths if p.suffix.lower() in suffixes]


class _DropArea(QWidget):
    """Empty-state panel: plain centered logo + hint + button, with no outline or
    other affordance. It just additionally accepts dropped input files."""

    clicked = Signal()
    files_dropped = Signal(list)  # list[Path]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

        from raggui.resources import logo_pixmap

        v = QVBoxLayout(self)
        v.addStretch(1)

        pixmap = logo_pixmap()
        if not pixmap.isNull():
            logo = QLabel()
            logo.setPixmap(pixmap.scaledToWidth(260, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)

        title = QLabel(workspace_title())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding-top: 8px;")
        v.addWidget(title)

        hint = QLabel("Add one or more inputs to get started.\nYou can also drag files here.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888; padding-top: 4px;")
        v.addWidget(hint)

        button = QPushButton("Add files…")
        button.clicked.connect(self.clicked)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if _inputs_from_urls(event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        inputs = _inputs_from_urls(event.mimeData().urls())
        if inputs:
            event.acceptProposedAction()
            self.files_dropped.emit(inputs)
        else:
            event.ignore()


class InputStepPanel(QWidget):
    """Per-input controls: step checkboxes, output base, overwrite, queue button."""

    add_to_queue_requested = Signal(object)  # emits self

    def __init__(self, input_path: Path, output_base: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._input = input_path

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(f"<b>{input_path.name}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(title)

        path_lbl = QLabel(str(input_path))
        path_lbl.setStyleSheet("color: #888;")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(path_lbl)

        root.addWidget(self._hline())

        steps_heading = QLabel("<b>Steps to run</b>")
        steps_heading.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(steps_heading)

        # Checkboxes come from the pipeline (config.yaml `steps:`). Selection is a
        # contiguous run from a legal start (see _refresh_plan / _on_toggle): you
        # can only begin at a step whose inputs are available, can't leave a hole,
        # and unchecking a step drops everything after it.
        self._steps = discover_steps()
        self._checks: list[QCheckBox] = []
        self._start: int | None = None
        self._end: int | None = None
        self._legal: list[bool] = []
        self._reach: list[int] = []
        self._syncing = False
        self._status = QLabel()
        self._status.setWordWrap(True)
        if self._steps:
            for i, step in enumerate(self._steps):
                cb = QCheckBox(step.label)
                needs = ", ".join(step.needs) or "—"
                cb.setToolTip(f"{step.name}  (env: {step.env})\nneeds: {needs}")
                cb.toggled.connect(lambda checked, idx=i: self._on_toggle(idx, checked))
                self._checks.append(cb)
                root.addWidget(cb)
            root.addWidget(self._status)
        else:
            self._status.setText("No pipeline steps found. Define them in config.yaml under `steps:`.")
            self._status.setStyleSheet("color: #d0883a;")
            root.addWidget(self._status)

        root.addWidget(self._hline())

        # Output base.
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output base:"))
        self._out_edit = QLineEdit(str(output_base) if output_base else "")
        self._out_edit.setReadOnly(True)
        self._out_edit.setPlaceholderText("Choose an output directory…")
        self._out_edit.setToolTip(self._out_edit.text())
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_output)
        out_row.addWidget(self._out_edit, 1)
        out_row.addWidget(browse)
        root.addLayout(out_row)

        self._overwrite = QCheckBox("Re-run steps even if their outputs already exist (--overwrite)")
        self._overwrite.setToolTip(
            "By default a step is skipped when its output is already present. Tick "
            "this to force the selected steps to rebuild for this input."
        )
        root.addWidget(self._overwrite)

        root.addStretch(1)

        # Queue button + transient confirmation.
        queue_row = QHBoxLayout()
        self._queue_btn = QPushButton("Add to Queue")
        self._queue_btn.clicked.connect(lambda: self.add_to_queue_requested.emit(self))
        self._added_lbl = QLabel("")
        self._added_lbl.setStyleSheet("color: #4caf50;")
        queue_row.addStretch(1)
        queue_row.addWidget(self._added_lbl)
        queue_row.addWidget(self._queue_btn)
        root.addLayout(queue_row)

        if self._steps:
            self._refresh_plan()

    # --- public API ---------------------------------------------------------

    @property
    def input_path(self) -> Path:
        return self._input

    @property
    def stem(self) -> str:
        return self._input.stem

    def selected_steps(self) -> list[str]:
        if self._start is None or self._end is None:
            return []
        return [self._steps[k].name for k in range(self._start, self._end + 1)]

    def output_base(self) -> Path | None:
        text = self._out_edit.text().strip()
        return Path(text) if text else None

    def overwrite(self) -> bool:
        return self._overwrite.isChecked()

    def adopt_selection(self, steps: list[str], output_base: Path | None, overwrite: bool) -> None:
        """Copy another panel's choices (used by Duplicate), if still valid here."""
        if output_base is not None:
            self._set_output_base(output_base)
        self._overwrite.setChecked(overwrite)
        self._refresh_plan()
        names = [s.name for s in self._steps]
        idxs = sorted(names.index(n) for n in steps if n in names)
        if idxs and idxs == list(range(idxs[0], idxs[-1] + 1)):
            s, e = idxs[0], idxs[-1]
            if self._legal[s] and e <= self._reach[s]:
                self._start, self._end = s, e
                self._sync()

    def confirm_added(self) -> None:
        self._added_lbl.setText("Added to queue ✓")

    # --- step gating (contiguous selection from a legal start) ---------------

    def _refresh_plan(self) -> None:
        """Recompute legal starts / reachability from the input + on-disk outputs,
        and reset the selection to the full runnable chain from the earliest start."""
        self._legal, self._reach = step_plan(self._input, self.output_base(), self.stem)
        starts = [i for i, ok in enumerate(self._legal) if ok]
        if starts:
            self._start = starts[0]
            self._end = self._reach[self._start]
        else:
            self._start = self._end = None
        self._sync()

    def _on_toggle(self, idx: int, checked: bool) -> None:
        if self._syncing:
            return
        s, e, legal, reach = self._start, self._end, self._legal, self._reach
        if checked:
            if s is None:
                if legal[idx]:
                    s = e = idx
            elif idx == e + 1 and e < reach[s]:
                e = idx                       # extend the end forward
            elif idx == s - 1 and legal[idx]:
                s, e = idx, min(e, reach[idx])  # extend the start backward
        else:
            if s is not None:
                if idx == s:                  # drop the leading step
                    nxt = s + 1
                    if nxt > e or not legal[nxt]:
                        s = e = None
                    else:
                        s, e = nxt, min(e, reach[nxt])
                elif s < idx <= e:            # drop a step -> drop everything after it
                    e = idx - 1
        self._start, self._end = s, e
        self._sync()

    def _sync(self) -> None:
        """Reflect the [start, end] selection onto the checkboxes (checked +
        enabled), then update the status line. Signals are blocked meanwhile."""
        self._syncing = True
        s, e = self._start, self._end
        for i, cb in enumerate(self._checks):
            selected = s is not None and s <= i <= e
            cb.setChecked(selected)
            if s is None:
                enabled = bool(self._legal[i])
            else:
                enabled = (
                    (s <= i <= e)
                    or (i == e + 1 and e < self._reach[s])
                    or (i == s - 1 and self._legal[i])
                )
            cb.setEnabled(enabled)
        self._syncing = False
        self._update_status()

    def _update_status(self) -> None:
        if not self._steps:
            return
        s, e = self._start, self._end
        if s is None:
            if any(self._legal):
                self._status.setText("Pick a starting step — only steps whose inputs are available are enabled.")
            else:
                self._status.setText(
                    "No step can start yet: the input doesn't match the first step and no existing "
                    "outputs were found. Choose the output directory to detect partial results."
                )
            self._status.setStyleSheet("color: #d0883a;")
        else:
            names = " → ".join(self._steps[k].label for k in range(s, e + 1))
            self._status.setText(f"Will run:  {names}")
            self._status.setStyleSheet("color: #4caf50;")

    # --- internals ----------------------------------------------------------

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    def _set_output_base(self, path: Path) -> None:
        self._out_edit.setText(str(path))
        self._out_edit.setToolTip(str(path))

    def _browse_output(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Choose output base", self._out_edit.text())
        if chosen:
            self._set_output_base(Path(chosen))
            save_output_base(Path(chosen))
            if self._steps:
                # Existing outputs in the new dir change which steps can start.
                self._refresh_plan()


@dataclass
class _OpenInput:
    path: Path
    panel: InputStepPanel


class InputsTab(QWidget):
    """Add inputs and queue each one's selected steps as an independent job."""

    def __init__(self, queue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._inputs: list[_OpenInput] = []
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # --- left: input list + actions ---
        left = QWidget(splitter)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.addWidget(QLabel("<b>Inputs</b>"))
        self.inputs_list = QListWidget()
        self.inputs_list.currentRowChanged.connect(self._on_selected)
        lv.addWidget(self.inputs_list, 1)

        self.add_btn = QPushButton("Add files…")
        self.add_btn.clicked.connect(self._browse_inputs)
        lv.addWidget(self.add_btn)
        edit_row = QHBoxLayout()
        self.duplicate_btn = QPushButton("Duplicate")
        self.duplicate_btn.clicked.connect(self._duplicate_current)
        self.duplicate_btn.setEnabled(False)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_current)
        self.remove_btn.setEnabled(False)
        edit_row.addWidget(self.duplicate_btn)
        edit_row.addWidget(self.remove_btn)
        lv.addLayout(edit_row)
        self.queue_all_btn = QPushButton("Add all to queue")
        self.queue_all_btn.clicked.connect(self._queue_all)
        self.queue_all_btn.setEnabled(False)
        lv.addWidget(self.queue_all_btn)

        # --- right: per-input panels + placeholder ---
        self.stack = QStackedWidget(splitter)
        self._placeholder = self._build_placeholder()
        self.stack.addWidget(self._placeholder)

        splitter.addWidget(left)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 860])
        layout.addWidget(splitter)

    # --- public API ---------------------------------------------------------

    def add_inputs(self, paths: list[Path]) -> None:
        if not paths:
            return
        first_row = len(self._inputs)
        for path in paths:
            self._add_input(path)
        if first_row < len(self._inputs):
            self.inputs_list.setCurrentRow(first_row)

    # --- internals: list management -----------------------------------------

    def _add_input(self, path: Path, at: int | None = None) -> InputStepPanel:
        panel = InputStepPanel(path, load_output_base())
        panel.add_to_queue_requested.connect(self._queue_panel)
        self.stack.addWidget(panel)
        if at is None:
            at = len(self._inputs)
        self._inputs.insert(at, _OpenInput(path, panel))
        self.inputs_list.insertItem(at, path.name)
        self.inputs_list.setCurrentRow(at)
        self.queue_all_btn.setEnabled(True)
        return panel

    def _browse_inputs(self) -> None:
        base = load_output_base()
        start = str(base.parent) if base else ""
        files, _ = QFileDialog.getOpenFileNames(self, "Add files", start, _input_filter())
        self.add_inputs([Path(f) for f in files])

    def _duplicate_current(self) -> None:
        row = self.inputs_list.currentRow()
        if not (0 <= row < len(self._inputs)):
            return
        src = self._inputs[row]
        panel = self._add_input(src.path, at=row + 1)
        panel.adopt_selection(
            src.panel.selected_steps(), src.panel.output_base(), src.panel.overwrite()
        )

    def _remove_current(self) -> None:
        row = self.inputs_list.currentRow()
        if not (0 <= row < len(self._inputs)):
            return
        item = self._inputs.pop(row)
        self.stack.removeWidget(item.panel)
        item.panel.deleteLater()
        self.inputs_list.takeItem(row)
        if not self._inputs:
            self.stack.setCurrentWidget(self._placeholder)
            self.remove_btn.setEnabled(False)
            self.duplicate_btn.setEnabled(False)
            self.queue_all_btn.setEnabled(False)

    def _on_selected(self, row: int) -> None:
        if 0 <= row < len(self._inputs):
            self.stack.setCurrentWidget(self._inputs[row].panel)
            self.remove_btn.setEnabled(True)
            self.duplicate_btn.setEnabled(True)
        else:
            self.stack.setCurrentWidget(self._placeholder)
            self.remove_btn.setEnabled(False)
            self.duplicate_btn.setEnabled(False)

    # --- internals: queueing -------------------------------------------------

    def _queue_panel(self, panel: InputStepPanel) -> None:
        steps = panel.selected_steps()
        if not steps:
            QMessageBox.information(self, "Add to Queue", "Select at least one step to run.")
            return
        output_base = panel.output_base()
        if output_base is None:
            QMessageBox.information(self, "Add to Queue", "Choose an output directory first.")
            return
        job = Job(
            input_path=panel.input_path,
            steps=steps,
            output_base=output_base,
            overwrite=panel.overwrite(),
        )
        self._queue.submit(job)
        panel.confirm_added()

    def _queue_all(self) -> None:
        for item in self._inputs:
            self._queue_panel(item.panel)

    # --- placeholder + drag/drop --------------------------------------------

    def _build_placeholder(self) -> QWidget:
        area = _DropArea()
        area.clicked.connect(self._browse_inputs)
        area.files_dropped.connect(self.add_inputs)
        return area

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        inputs = _inputs_from_urls(event.mimeData().urls())
        if inputs:
            self.add_inputs(inputs)
            event.acceptProposedAction()
