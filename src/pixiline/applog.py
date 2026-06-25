"""GUI / orchestrator logging, via loguru.

A per-session log file plus uncaught-exception capture, so a crash or unexpected
event leaves a durable record even when the live terminal view is gone. This is
the GUI's *own* log (job/step events, errors); the full tool output of a run is
written separately per recording (see jobs.termlog).

The file lives in ``~/.pixiline/logs/pixiline-<timestamp>.log``. Import ``log`` and
call ``log.info(...)`` / ``log.error(...)`` / ``log.exception(...)`` (loguru, so
messages use ``{}`` formatting or f-strings).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from loguru import logger as log

_session_path: Path | None = None


def setup() -> Path | None:
    """Add a file sink for this GUI session (idempotent). Returns the path."""
    global _session_path
    if _session_path is not None:
        return _session_path
    try:
        log_dir = Path.home() / ".pixiline" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        path = log_dir / f"pixiline-{stamp}.log"
        log.add(
            path,
            level="INFO",
            enqueue=True,  # thread-safe + flushed
            backtrace=True,
            diagnose=False,  # don't dump local variable values into tracebacks
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {message}",
        )
        _session_path = path
        log.info("pixiline session started")
        return path
    except OSError:
        return None


def install_excepthook() -> None:
    """Route uncaught exceptions to the log (keeping the default handler too), so a
    crash leaves a traceback on disk."""
    previous = sys.excepthook

    def hook(exc_type, exc, tb) -> None:
        try:
            log.opt(exception=(exc_type, exc, tb)).error("Uncaught exception")
        finally:
            previous(exc_type, exc, tb)

    sys.excepthook = hook
