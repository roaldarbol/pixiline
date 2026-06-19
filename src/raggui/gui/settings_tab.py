"""Settings tab: edit ``config.yaml`` — the pipeline's single source of truth.

The form is generated from the file itself: each top-level section becomes a group
box, and each scalar leaf becomes a widget chosen by its value's type (bool→check,
int→spin, float→double-spin, str/list→line edit). End-of-line comments become
tooltips. Edits are written back with ruamel.yaml so comments/layout survive.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from raggui.config import comment_for, is_section, load_config, save_config
from raggui.pipeline import STEPS_KEY

_INT_RANGE = (-1_000_000_000, 1_000_000_000)
_FLOAT_RANGE = (-1.0e12, 1.0e12)

#: config.yaml keys the Settings tab does not edit (structure, not tunable knobs).
_RESERVED_KEYS = frozenset({STEPS_KEY})


def _prettify(key: Any) -> str:
    return str(key).replace("-", " ").replace("_", " ").strip().capitalize()


class _Binding:
    """Connects one config leaf (section→key) to its editing widget."""

    def __init__(self, section: Any, key: Any, widget: QWidget, kind: str) -> None:
        self.section = section  # the parent CommentedMap (we write back into it)
        self.key = key
        self.widget = widget
        self.kind = kind  # bool | int | float | str | list

    def read_into_doc(self) -> None:
        w = self.widget
        if self.kind == "bool":
            value: Any = w.isChecked()
        elif self.kind in ("int", "float"):
            value = w.value()
        elif self.kind == "list":
            text = w.text().strip()
            value = [p.strip() for p in text.split(",") if p.strip()] if text else []
        else:
            value = w.text()
        self.section[self.key] = value


class SettingsTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: Any = None
        self._bindings: list[_Binding] = []
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        intro = QLabel(
            "<b>Pipeline configuration</b> — these settings apply to every recording "
            "and are saved to <code>config.yaml</code>."
        )
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(self._scroll, 1)

        save_row = QHBoxLayout()
        self._save_btn = QPushButton("Save settings")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._save)
        self._status = QLabel("")
        self._status.setStyleSheet("color: #4caf50;")
        save_row.addStretch(1)
        save_row.addWidget(self._status)
        save_row.addWidget(self._save_btn)
        root.addLayout(save_row)

        self._reload()

    # --- build from the document --------------------------------------------

    def _reload(self) -> None:
        try:
            self._doc = load_config()
        except OSError as exc:
            QMessageBox.critical(self, "Settings", f"Could not read config.yaml:\n\n{exc}")
            self._doc = None
            return

        self._loading = True
        self._bindings = []
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        general: list[tuple[Any, Any]] = []  # top-level scalars, if any
        for key, value in (self._doc.items() if self._doc else []):
            if key in _RESERVED_KEYS:
                continue  # the pipeline definition (steps:) is structure, not a knob
            if is_section(value):
                outer.addWidget(self._build_group(_prettify(key), value))
            else:
                general.append((key, value))
        if general:
            grp = QGroupBox("General")
            form = QFormLayout(grp)
            for key, value in general:
                self._add_field(form, self._doc, key, value)
            outer.insertWidget(0, grp)

        outer.addStretch(1)
        self._scroll.setWidget(container)
        self._loading = False
        self._save_btn.setEnabled(False)
        self._status.clear()

    def _build_group(self, title: str, section: Any) -> QGroupBox:
        box = QGroupBox(title)
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for key, value in section.items():
            if is_section(value):
                continue  # only scalar leaves are edited (keeps it to flat sections)
            self._add_field(form, section, key, value)
        return box

    def _add_field(self, form: QFormLayout, section: Any, key: Any, value: Any) -> None:
        widget, kind = self._make_widget(value)
        tooltip = comment_for(section, key)
        label = QLabel(_prettify(key))
        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        form.addRow(label, widget)
        self._bindings.append(_Binding(section, key, widget, kind))

    def _make_widget(self, value: Any) -> tuple[QWidget, str]:
        # bool before int: bool is a subclass of int.
        if isinstance(value, bool):
            w = QCheckBox()
            w.setChecked(value)
            w.toggled.connect(self._on_edited)
            return w, "bool"
        if isinstance(value, int):
            w = QSpinBox()
            w.setRange(*_INT_RANGE)
            w.setValue(value)
            w.valueChanged.connect(self._on_edited)
            return w, "int"
        if isinstance(value, float):
            w = QDoubleSpinBox()
            w.setRange(*_FLOAT_RANGE)
            w.setDecimals(4)
            w.setSingleStep(0.01)
            w.setValue(value)
            w.valueChanged.connect(self._on_edited)
            return w, "float"
        if isinstance(value, (list, tuple)):
            w = QLineEdit(", ".join(str(v) for v in value))
            w.textChanged.connect(self._on_edited)
            return w, "list"
        w = QLineEdit("" if value is None else str(value))
        w.textChanged.connect(self._on_edited)
        return w, "str"

    # --- save ----------------------------------------------------------------

    def _save(self) -> None:
        if self._doc is None:
            return
        for binding in self._bindings:
            binding.read_into_doc()
        try:
            save_config(self._doc)
        except OSError as exc:
            QMessageBox.critical(self, "Settings", f"Could not write config.yaml:\n\n{exc}")
            return
        self._save_btn.setEnabled(False)
        self._status.setText("Saved ✓")

    # --- Qt overrides --------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._reload()

    def _on_edited(self, *_args) -> None:
        if self._loading:
            return
        self._save_btn.setEnabled(True)
        self._status.clear()
