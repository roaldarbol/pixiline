"""Entry point for the pipeline GUI (``pixi run gui``).

Adds ``src/`` to ``sys.path`` so the ``gui`` package is importable when run as a
bare script, then launches the Qt app.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from raggui.app import main  # noqa: E402 (after sys.path setup)

if __name__ == "__main__":
    raise SystemExit(main())
