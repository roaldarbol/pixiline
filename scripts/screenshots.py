"""Generate the documentation screenshots — headless, framed, light + dark.

Renders Pixiline's real widgets via Qt's offscreen platform, grabs each to a
pixmap, and composites it onto a flowing Pixi-branded aurora backdrop (navy →
blue → gold) with rounded corners and a soft drop shadow (the "shots.so /
Screely" look) — all with Qt, no external service. Run with
``pixi run screenshots``; output lands in ``docs/assets/<name>-<light|dark>.png``.

Everything is synthetic: a couple of example pipelines are built directly as
:class:`~pixiline.manifest.Pipeline` dataclasses (no ``pixi`` subprocess, no real
workspace on disk), the workbench is populated, and the Jobs view is driven by
emitting the queue's signals with hand-set states — so a fake "run" shows a
progressing job and a live terminal without launching any process.

One ``MainWindow`` is built and reused for every shot; building a window per shot
leaks palette-watch filters and slows to a crawl (same reasoning as croppy's
generator, which this is adapted from).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QGraphicsScene,
    QWidget,
)

from pixiline.jobs.job import Job, JobState
from pixiline.manifest import Arg, Pipeline, Step

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "docs" / "assets"

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _load_font(app: QApplication) -> None:
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).exists():
            fid = QFontDatabase.addApplicationFont(candidate)
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                app.setFont(QFont(families[0], 9))
                return


def _dark_palette() -> QPalette:
    p = QPalette()
    window, base, text = QColor("#1f1f24"), QColor("#17171b"), QColor("#e6e6ea")
    muted = QColor("#75757f")
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, window)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, base)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8a8a95"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#5773ff"))  # Pixi blue
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, muted)
    return p


def _set_theme(app: QApplication, *, dark: bool) -> None:
    from pixiline.gui.theme import apply_app_theme

    app.setPalette(_dark_palette() if dark else app.style().standardPalette())
    apply_app_theme()
    for _ in range(3):  # let the deferred palette-watch re-style settle
        app.processEvents()


# --- example pipelines ------------------------------------------------------


def _behaviour_pipeline() -> Pipeline:
    """A branching animal-behaviour pipeline: convert → (track ∥ pose) → analyse
    → report. The diamond gives the DAG something to show, and the tunable args
    (with defaults / choices) populate the Settings form."""
    out = "{{ output }}/{{ stem }}"
    steps = (
        Step(
            name="convert",
            env="default",
            description="Transcode the raw recording to a normalised MP4 the rest of "
            "the pipeline reads from.",
            args=(Arg("fps", default="30"),),
            inputs=("{{ input }}",),
            outputs=(f"{out}/raw.mp4",),
        ),
        Step(
            name="track",
            env="gpu",
            description="Multi-animal tracking — one row per animal per frame.",
            args=(
                Arg("tracker", default="bytetrack", choices=("bytetrack", "botsort")),
                Arg("confidence", default="0.5"),
            ),
            inputs=(f"{out}/raw.mp4",),
            outputs=(f"{out}/tracks.csv",),
        ),
        Step(
            name="pose",
            env="gpu",
            description="Pose estimation — body-part keypoints for every frame.",
            args=(Arg("model", default="hrnet", choices=("hrnet", "resnet50", "vitpose")),),
            inputs=(f"{out}/raw.mp4",),
            outputs=(f"{out}/pose.h5",),
        ),
        Step(
            name="analyse",
            env="stats",
            description="Combine tracks + pose into per-animal behavioural features.",
            args=(Arg("smoothing", default="savgol", choices=("none", "savgol", "median")),),
            inputs=(f"{out}/tracks.csv", f"{out}/pose.h5"),
            outputs=(f"{out}/summary.csv",),
        ),
        Step(
            name="report",
            env="stats",
            description="Render a self-contained HTML report of the run.",
            args=(),
            inputs=(f"{out}/summary.csv",),
            outputs=(f"{out}/report.html",),
        ),
    )
    return Pipeline(
        root=Path("behaviour-pipeline"),
        name="behaviour-pipeline",
        steps=steps,
        environments=frozenset({"default", "gpu", "stats"}),
    )


# --- window population -------------------------------------------------------


def _add_pipeline(win: QWidget, pipeline: Pipeline, name: str):
    """Inject a synthetic pipeline into the window the way ``MainWindow._add_pipeline``
    does, but without the ``pixi task list`` subprocess."""
    from pixiline.gui.pipeline_view import PipelineView

    view = PipelineView(pipeline, win._queue)
    view.display_name = name
    win._pipelines.append(pipeline)
    win._pipeline_views.append(view)
    win._workbench.addWidget(view)
    win._sidebar.add_pipeline(name)  # selects it → workbench shows this view
    return view


def _populate_workbench(view) -> None:
    view._out_edit.setText("D:/experiments/2026-06/output")
    view._out_edit.setToolTip(view._out_edit.text())
    view.add_inputs(
        [
            Path("Exp01_Day01_Manon.mp4"),
            Path("Exp01_Day02_Manon.mp4"),
            Path("Exp02_Day01_Pierre.mp4"),
        ]
    )
    view._on_dag_focus("pose")  # show a step's description under the DAG


# A short, colourful "pixi run" transcript for the running job's terminal. Raw
# ANSI (green/blue/bold) so the pyte-backed TerminalView renders real colour.
# Kept ASCII-only: the offscreen font used for the grab has no glyphs for box-
# drawing or check marks, so those would render as tofu boxes in the shot.
_G = "\x1b[32m"
_B = "\x1b[34m"
_D = "\x1b[90m"
_BOLD = "\x1b[1m"
_R = "\x1b[0m"
_RUNNING_LOG = (
    f"{_D}$ pixi run -e default convert Exp01_Day01_Manon.mp4{_R}\n"
    f"{_G}[ok]{_R} convert  raw.mp4 written (30 fps, 12,004 frames)\n"
    f"{_D}$ pixi run -e gpu track Exp01_Day01_Manon.mp4{_R}\n"
    f"{_G}[ok]{_R} track    tracks.csv - 3 animals, 12,004 frames\n"
    f"{_D}$ pixi run -e gpu pose Exp01_Day01_Manon.mp4{_R}\n"
    f"{_BOLD}pose{_R}  loading {_B}hrnet{_R} weights...\n"
    f"  inferring keypoints  {_B}[###############.........]{_R}  64%  7723/12004  "
    f"{_D}eta 0:41{_R}\n"
)


def _stage_jobs(win: QWidget, pipeline: Pipeline) -> None:
    """Submit a batch and drive it to a mixed set of states by emitting the queue's
    signals directly (no Worker, so nothing actually runs)."""
    queue = win._queue
    panel = win._jobs_panel
    steps = [s.name for s in pipeline.steps]

    def make(name: str) -> Job:
        job = Job(
            pipeline=pipeline,
            input_path=Path(name),
            output_base=Path("D:/experiments/2026-06/output"),
            steps=steps,
            pipeline_label=pipeline.name,
        )
        queue.submit(job)  # → QUEUED, appears in the Queued group
        return job

    done1 = make("Exp01_Day01_Manon.mp4")
    running = make("Exp01_Day02_Manon.mp4")
    pending = make("Exp02_Day01_Pierre.mp4")
    queued = make("Exp02_Day02_Pierre.mp4")  # noqa: F841 — stays in Queued

    # A finished job.
    done1.state = JobState.DONE
    done1.current_step = len(done1.steps)
    queue.job_finished.emit(done1.id)

    # A running job with a live terminal + partial progress.
    running.state = JobState.RUNNING
    running.current_step = 2  # "pose"
    running.log = _RUNNING_LOG
    queue.job_started.emit(running.id)  # moves to Running + shows its log
    queue.job_step.emit(running.id, 2, "pose")
    queue.job_progress.emit(running.id, 2 / len(running.steps) + 0.128)

    # A pending job.
    pending.state = JobState.PENDING
    queue.job_pending.emit(pending.id)

    panel._log_view._render()  # force a paint of the terminal for the grab


# --- framing (Pixi-branded aurora) ------------------------------------------


def _paint_aurora(painter: QPainter, w: int, h: int, *, dark: bool) -> None:
    """Fill ``(w, h)`` with a flowing Pixi-palette aurora + a corner glow."""
    base = QLinearGradient(0, 0, w, h)
    if dark:
        stops = [
            (0.0, "#001330"),  # navy
            (0.32, "#0b2352"),
            (0.56, "#3a2f6a"),
            (0.80, "#8a4a3f"),
            (1.0, "#d98a2a"),  # toward gold
        ]
    else:
        stops = [
            (0.0, "#5773ff"),  # Pixi blue
            (0.30, "#7a7bf0"),
            (0.55, "#c76fb0"),
            (0.80, "#ff8a5c"),  # Pixi red-ish
            (1.0, "#ffd432"),  # Pixi gold
        ]
    for pos, hex_color in stops:
        base.setColorAt(pos, QColor(hex_color))
    painter.fillRect(QRect(0, 0, w, h), QBrush(base))

    glow = QRadialGradient(w * 0.30, h * 0.18, max(w, h) * 0.80)
    inner = QColor("#ffffff")
    inner.setAlpha(70 if not dark else 45)
    outer = QColor("#ffffff")
    outer.setAlpha(0)
    glow.setColorAt(0.0, inner)
    glow.setColorAt(1.0, outer)
    painter.fillRect(QRect(0, 0, w, h), QBrush(glow))


def _frame(pix: QPixmap, *, dark: bool, pad: int = 84) -> QImage:
    """Composite ``pix`` onto the aurora backdrop with rounded corners + shadow."""
    w, h = pix.width() + pad * 2, pix.height() + pad * 2
    target = QImage(w, h, QImage.Format.Format_ARGB32)

    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _paint_aurora(painter, w, h, dark=dark)
    painter.end()

    rounded = QPixmap(pix.size())
    rounded.fill(Qt.GlobalColor.transparent)
    rp = QPainter(rounded)
    rp.setRenderHint(QPainter.RenderHint.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, pix.width(), pix.height()), 12, 12)
    rp.setClipPath(clip)
    rp.drawPixmap(0, 0, pix)
    rp.end()

    scene = QGraphicsScene()
    scene.setBackgroundBrush(Qt.GlobalColor.transparent)
    item = scene.addPixmap(rounded)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(46)
    shadow.setColor(QColor(0, 0, 0, 150))
    shadow.setOffset(0, 18)
    item.setGraphicsEffect(shadow)
    item.setPos(pad, pad)

    p2 = QPainter(target)
    p2.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(p2, QRectF(0, 0, w, h), QRectF(0, 0, w, h))
    p2.end()
    return target


def _save(img: QImage, name: str, *, dark: bool) -> None:
    out = ASSETS / f"{name}-{'dark' if dark else 'light'}.png"
    img.save(str(out))
    print(f"wrote {out.relative_to(REPO)}")


def _launch_icon(*, dark: bool, tile: int = 460, pad: int = 130) -> QImage:
    """The app icon as a macOS-style rounded-square tile on the aurora backdrop."""
    logo = QPixmap(str(REPO / "src" / "pixiline" / "assets" / "icons" / "orchestrator-512.png"))

    tilepix = QPixmap(tile, tile)
    tilepix.fill(Qt.GlobalColor.transparent)
    tp = QPainter(tilepix)
    tp.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = tile * 0.2237  # the macOS "squircle" corner ratio
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, tile, tile), radius, radius)
    tp.setClipPath(path)
    fill = QLinearGradient(0, 0, 0, tile)
    fill.setColorAt(0.0, QColor("#ffffff"))
    fill.setColorAt(1.0, QColor("#eef1fb"))
    tp.fillRect(QRect(0, 0, tile, tile), QBrush(fill))
    margin = int(tile * 0.05)
    art = logo.scaled(
        tile - 2 * margin,
        tile - 2 * margin,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    tp.drawPixmap((tile - art.width()) // 2, (tile - art.height()) // 2, art)
    tp.end()

    side = tile + pad * 2
    target = QImage(side, side, QImage.Format.Format_ARGB32)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    _paint_aurora(painter, side, side, dark=dark)
    painter.end()

    scene = QGraphicsScene()
    scene.setBackgroundBrush(Qt.GlobalColor.transparent)
    item = scene.addPixmap(tilepix)
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(60)
    shadow.setColor(QColor(0, 0, 0, 150))
    shadow.setOffset(0, 24)
    item.setGraphicsEffect(shadow)
    item.setPos(pad, pad)
    p2 = QPainter(target)
    p2.setRenderHint(QPainter.RenderHint.Antialiasing)
    scene.render(p2, QRectF(0, 0, side, side), QRectF(0, 0, side, side))
    p2.end()
    return target


# --- driver -----------------------------------------------------------------


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    _load_font(app)

    from pixiline.gui.main_window import MainWindow

    pipeline = _behaviour_pipeline()

    win = MainWindow()
    win.resize(1320, 840)
    view = _add_pipeline(win, pipeline, pipeline.name)
    _populate_workbench(view)
    _stage_jobs(win, pipeline)
    win.show()
    app.processEvents()

    for dark in (False, True):
        _set_theme(app, dark=dark)

        # The loaded-pipeline workbench (activity → Pipelines).
        win._activity.select("pipelines")
        app.processEvents()
        _save(_frame(win.grab(), dark=dark), "app-pipeline", dark=dark)

        # The DAG on its own (the signature widget).
        _save(_frame(view._dag.grab(), dark=dark, pad=48), "dag", dark=dark)

        # The Jobs view (activity → Jobs), with the running terminal.
        win._activity.select("jobs")
        win._jobs_panel._log_view._render()
        app.processEvents()
        _save(_frame(win.grab(), dark=dark), "app-jobs", dark=dark)

        # The empty drop screen (first-run look) — clear the sidebar list and show
        # the drop widget, then restore the loaded pipeline afterwards.
        win._activity.select("pipelines")
        win._sidebar.list.blockSignals(True)
        win._sidebar.list.clear()
        win._sidebar.list.blockSignals(False)
        win._workbench.setCurrentWidget(win._drop)
        app.processEvents()
        _save(_frame(win.grab(), dark=dark), "app-drop", dark=dark)
        win._sidebar.add_pipeline(pipeline.name)  # re-add → reselects the view
        win._workbench.setCurrentWidget(view)

        _save(_launch_icon(dark=dark), "launch-icon", dark=dark)
        app.processEvents()

    # Avoid a slow interpreter-exit waiting on Qt threads.
    os._exit(0)


if __name__ == "__main__":
    main()
