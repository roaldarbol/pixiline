"""Offscreen construction smoke test — builds the UI without a display and exits.
Run with: pixi run python src/pixiline/_smoketest.py

Verifies imports, manifest loading (against ../sleep-staging if present), command
building, and that the window stands up and a pipeline view instantiates. Not a
unit test suite; just a fast "does it stand up" check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from pixiline.gui.main_window import MainWindow  # noqa: E402
from pixiline.manifest import build_command, load_pipeline  # noqa: E402

# The example pipeline lives next to the pixiline repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE = _REPO_ROOT / "sleep-staging"


def main() -> int:
    app = QApplication.instance() or QApplication([])

    win = MainWindow()
    win.show()
    app.processEvents()
    print("OK: window built (empty state =", win._workbench.currentWidget() is win._drop, ")")

    if (_PIPELINE / "pixi.toml").is_file():
        pipeline = load_pipeline(_PIPELINE)
        print("pipeline:", pipeline.name)
        print("steps   :", [s.name for s in pipeline.order()])
        print("run args:", [a.name for a in pipeline.required_inputs()])
        predict = pipeline.step("predict")
        if predict is not None:
            cmd = build_command(predict, {"stem": "clip", "output": "out", "input": "clip.mp4"})
            print("cmd     :", " ".join(cmd))
        # Load it into the window and add an input.
        win._add_pipeline(_PIPELINE)
        app.processEvents()
        view = win._pipeline_views[-1]
        view.add_inputs([Path("clip.mp4")])
        app.processEvents()
        win._activity.select("jobs")  # switch to the global Jobs view
        app.processEvents()
        print("OK: pipeline view + activity views built (count =", win._views.count(), ")")
    else:
        print("(no sleep-staging pipeline next to repo; skipped manifest load)")

    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
