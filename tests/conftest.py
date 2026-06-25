"""Shared fixtures and pipeline builders for the test suite.

The orchestration core is split into two layers for testing:

* pure data/logic (``manifest``, ``jobs.job``, ``jobs.termlog``, ``paths``) needs
  no Qt and is tested directly;
* the Qt-touching pieces (``jobs.queue``, ``config``) get a ``QApplication`` from
  ``pytest-qt`` and, for ``config``, a throwaway ``QSettings`` store so tests never
  read or write the developer's real preferences.
"""

from __future__ import annotations

import pytest

from pixiline.manifest import Arg, Pipeline, Step


def make_step(
    name: str,
    *,
    env: str = "default",
    description: str = "",
    args: tuple[Arg, ...] = (),
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
) -> Step:
    return Step(
        name=name,
        env=env,
        description=description,
        args=args,
        inputs=inputs,
        outputs=outputs,
    )


@pytest.fixture
def sample_pipeline(tmp_path) -> Pipeline:
    """A small but realistic linear pipeline:

        motion -> track -> export -> report (optional)

    Edges are derived purely from outputs feeding inputs. ``motion`` reads the
    external user file (``{{ input }}``) and carries the only required arg plus
    two tunable settings; the rest read prior outputs.
    """
    motion = make_step(
        "motion",
        env="gpu",
        description="Detect motion",
        args=(
            Arg("input"),  # required (no default) -> run identity
            Arg("fps", default="30"),
            Arg("model", default="base", choices=("base", "large")),
        ),
        inputs=("{{ input }}",),
        outputs=("{{ output }}/{{ stem }}/motion.mp4",),
    )
    track = make_step(
        "track",
        env="gpu",
        description="Track blobs",
        args=(Arg("threshold", default="0.5"),),
        inputs=("{{ output }}/{{ stem }}/motion.mp4",),
        outputs=("{{ output }}/{{ stem }}/track.csv",),
    )
    export = make_step(
        "export",
        env="cpu",
        description="Export table",
        inputs=("{{ output }}/{{ stem }}/track.csv",),
        outputs=("{{ output }}/{{ stem }}/export.parquet",),
    )
    report = make_step(
        "report",
        env="cpu",
        description="[optional] Render an HTML report",
        inputs=("{{ output }}/{{ stem }}/export.parquet",),
        outputs=("{{ output }}/{{ stem }}/report.html",),
    )
    return Pipeline(
        root=tmp_path,
        name="spider-sleep",
        steps=(motion, track, export, report),
        environments=frozenset({"gpu", "cpu"}),
    )


@pytest.fixture
def temp_settings(qapp, tmp_path, monkeypatch):
    """Point ``QSettings()`` at a throwaway INI file under ``tmp_path`` so the
    config round-trip tests never touch the real user store."""
    from PySide6.QtCore import QCoreApplication, QSettings

    QCoreApplication.setOrganizationName("pixiline-test")
    QCoreApplication.setApplicationName("pixiline-test")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    QSettings().clear()
    yield
    QSettings().clear()
