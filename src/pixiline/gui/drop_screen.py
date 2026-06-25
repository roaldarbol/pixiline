"""Empty-state screen: drop (or browse to) a ``pixi.toml`` to add a pipeline.

Shows the pixiline logo and a hint; accepts a dropped ``pixi.toml`` file or a folder
that contains one, and emits the pipeline's root directory.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pixiline.resources import logo_pixmap


def pipeline_root_from(path: Path) -> Path | None:
    """The pipeline root for a dropped path: the folder itself if it holds a
    ``pixi.toml``, or the parent of a dropped ``pixi.toml``. ``None`` otherwise."""
    if path.is_dir() and (path / "pixi.toml").is_file():
        return path
    if path.is_file() and path.name == "pixi.toml":
        return path.parent
    return None


def _roots_from_urls(urls) -> list[Path]:
    roots = []
    for url in urls:
        if not url.isLocalFile():
            continue
        root = pipeline_root_from(Path(url.toLocalFile()))
        if root is not None and root not in roots:
            roots.append(root)
    return roots


class DropScreen(QWidget):
    """Centered logo + hint + button; accepts a dropped pixi.toml / pipeline folder."""

    pipeline_chosen = Signal(object)  # Path (pipeline root)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        v = QVBoxLayout(self)
        v.addStretch(1)

        pixmap = logo_pixmap()
        if not pixmap.isNull():
            logo = QLabel()
            logo.setPixmap(pixmap.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(logo)

        title = QLabel("pixiline")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding-top: 8px;")
        v.addWidget(title)

        hint = QLabel(
            "Drop a pixi.toml here to add a pipeline.\n"
            "You can add several and queue jobs from each."
        )
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #888; padding-top: 4px;")
        v.addWidget(hint)

        button = QPushButton("Add pipeline…")
        button.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(button)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)

    def _browse(self) -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            self, "Select a pipeline's pixi.toml", "", "Pixi manifest (pixi.toml);;All files (*)"
        )
        if chosen:
            root = pipeline_root_from(Path(chosen))
            if root is not None:
                self.pipeline_chosen.emit(root)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.MouseButton.LeftButton:
            self._browse()
            event.accept()
            return
        super().mousePressEvent(event)

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
