"""Offscreen construction smoke test — builds the whole UI without a display and
exits. Run with: pixi run -e gui python src/raggui/_smoketest.py

Verifies imports, widget construction, config.yaml round-trip, step discovery, and
command building. Not a unit test suite; just a fast "does it stand up" check.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from raggui.config import is_section, load_config  # noqa: E402
from raggui.gui.main_window import MainWindow  # noqa: E402
from raggui.paths import workspace_title  # noqa: E402
from raggui.pipeline import build_command, discover_steps  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])

    print("title  :", workspace_title())

    # config.yaml round-trips; report its top-level sections.
    doc = load_config()
    sections = [k for k, v in doc.items() if is_section(v)]
    print("config sections:", ", ".join(str(s) for s in sections))

    # Discovered steps + a sample command (empty list if the segmentation env is
    # disabled or pixi isn't reachable — that's expected here, not a failure).
    steps = discover_steps()
    print("steps  :", ", ".join(s.name for s in steps) or "(none discovered)")
    if steps:
        s = steps[0]
        print("cmd    :", " ".join(build_command(s.name, Path("clip.mp4"), Path("out"), "clip", overwrite=True)))
        print("steps detail:", [(x.name, x.env, "input" if x.wants_input else "tree") for x in steps])

    # Build the full window.
    win = MainWindow()
    win.show()
    app.processEvents()
    assert win.tabs.count() == 3, "expected Inputs / Jobs / Settings tabs"
    win.inputs_tab.add_inputs([Path("clip.mp4")])
    app.processEvents()
    print("OK: window built with tabs:", [win.tabs.tabText(i) for i in range(win.tabs.count())])
    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
