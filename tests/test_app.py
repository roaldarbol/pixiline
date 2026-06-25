"""Tests for the CLI entry point.

Only the ``--version`` path is exercised: it is handled before any Qt setup, so
it runs headlessly. Launching the GUI itself needs a display and is out of scope.
"""

from __future__ import annotations

import pytest

from pixiline import __version__
from pixiline.app import main


def test_version_flag_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert f"pixiline {__version__}" in capsys.readouterr().out


def test_help_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "Pixi-pipeline manager" in capsys.readouterr().out
