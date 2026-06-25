"""Qt application bootstrap for the pipeline GUI."""

from __future__ import annotations

import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pixiline import applog
from pixiline.gui.main_window import MainWindow
from pixiline.resources import app_icon


def main() -> int:
    """Start the Qt event loop and return its exit code."""
    applog.setup()
    applog.install_excepthook()  # a crash leaves a traceback in the GUI log
    qt_app = QApplication.instance() or QApplication(sys.argv)
    qt_app.setApplicationName("pixiline")
    qt_app.setApplicationDisplayName("pixiline")
    # organizationName completes the QSettings storage path (see pixiline.config).
    qt_app.setOrganizationName("PixiPipelineOrchestrator")
    qt_app.setWindowIcon(app_icon())

    window = MainWindow()
    window.show()

    # Cancel running jobs on exit so we don't orphan pixi/processing subprocesses.
    qt_app.aboutToQuit.connect(window.shutdown)

    # Make Ctrl+C in the terminal quit gracefully. Qt's event loop runs in C++ and
    # never returns to Python to deliver the signal, so we quit on SIGINT and keep
    # a no-op timer ticking to give the interpreter a chance to run the handler.
    signal.signal(signal.SIGINT, lambda *_: qt_app.quit())
    keepalive = QTimer(qt_app)
    keepalive.timeout.connect(lambda: None)
    keepalive.start(200)

    return qt_app.exec()
