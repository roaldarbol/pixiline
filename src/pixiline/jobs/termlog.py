"""Write a clean plain-text log of a job's output.

Programs redraw progress bars with carriage returns and colour them with ANSI
codes, so the raw stream has thousands of intermediate states per line. This
settles each line to its *final* form (after the carriage-return overwrites and
line-erases) and strips ANSI, writing one tidy line per real newline — so the log
file has the finished value of each line, not the progress spam.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

# CSI escape: ESC [ <params> <final-letter>
_CSI = re.compile(r"\x1b\[([0-9;?]*)([A-Za-z])")


class SettledLog:
    """Feed raw terminal output; it writes settled plain-text lines to a file."""

    def __init__(self, path: Path) -> None:
        self._fh = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = path.open("w", encoding="utf-8")
        except OSError:
            self._fh = None  # logging is best-effort; never break the run
        self._line = ""
        self._col = 0

    def feed(self, text: str) -> None:
        if self._fh is None:
            return
        i, n = 0, len(text)
        while i < n:
            c = text[i]
            if c == "\x1b":
                m = _CSI.match(text, i)
                if m:
                    self._apply_csi(m.group(1), m.group(2))
                    i = m.end()
                    continue
                i += 1  # lone/other escape — drop it
                continue
            if c == "\r":
                self._col = 0
            elif c == "\n":
                self._commit_line()
            elif c == "\t":
                self._write(" " * (8 - (self._col % 8)))
            elif c == "\b":
                self._col = max(0, self._col - 1)
            elif c >= " ":
                self._write(c)
            i += 1

    def close(self) -> None:
        if self._fh is None:
            return
        try:
            if self._line.strip():
                self._commit_line()
            self._fh.close()
        except OSError:
            pass
        self._fh = None

    # --- internals ----------------------------------------------------------

    def _write(self, s: str) -> None:
        for ch in s:
            if self._col < len(self._line):
                self._line = self._line[: self._col] + ch + self._line[self._col + 1 :]
            else:
                self._line += ch
            self._col += 1

    def _commit_line(self) -> None:
        try:
            self._fh.write(self._line.rstrip() + "\n")
            self._fh.flush()  # so the log survives even if a step crashes
        except OSError:
            pass
        self._line = ""
        self._col = 0

    def _apply_csi(self, params: str, final: str) -> None:
        if final == "K":  # erase in line
            mode = params or "0"
            if mode == "0":
                self._line = self._line[: self._col]
            elif mode == "1":
                self._line = " " * self._col + self._line[self._col :]
            elif mode == "2":
                self._line = ""
        elif final == "G":  # cursor to column (1-based)
            with contextlib.suppress(ValueError):
                self._col = max(0, int(params or "1") - 1)
        # other sequences (SGR colour 'm', cursor moves, etc.) are dropped
