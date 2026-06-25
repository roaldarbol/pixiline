"""A tiny label that shows a confirmation message, then clears itself.

(Ported from croppy.)
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class StatusFlash(QLabel):
    """Green confirmation text that auto-clears after a short delay.

    Used next to the "Add to Queue" button so a click gives immediate feedback
    without switching to the Jobs tab. Calling :meth:`flash` again restarts the
    timer, so rapid clicks keep the latest message visible.
    """

    def __init__(self, parent: QWidget | None = None, *, timeout_ms: int = 4000) -> None:
        super().__init__(parent)
        self._timeout_ms = timeout_ms
        self.setStyleSheet("color: #4caf50;")  # green, matches the Settings "Saved ✓"
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)

    def flash(self, text: str) -> None:
        self.setText(text)
        self._timer.start(self._timeout_ms)
