"""A small terminal-emulator log view.

Program output is fed through a pyte screen, so carriage returns / cursor moves
update the log *in place* (a progress bar stays one refreshing line instead of
scrolling thousands of lines) and ANSI colour codes render as real colours. Only
the screen lines pyte marks dirty are repainted, and on a throttle, so it stays
cheap even for very chatty, hours-long runs.
"""

from __future__ import annotations

import pyte
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

_COLS, _ROWS = 120, 300        # terminal size (rows = how much scrollback is kept)
_REFRESH_MS = 80               # repaint at most ~12x/sec

_DEFAULT_BG = "#1e1e1e"
_DEFAULT_FG = "#d4d4d4"
_ANSI = {
    "black": "#5c6370", "red": "#e06c75", "green": "#98c379", "brown": "#d19a66",
    "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#abb2bf",
}
_ANSI_BRIGHT = {
    "black": "#7f8696", "red": "#ff7b86", "green": "#b5e890", "brown": "#e5c07b",
    "blue": "#7cc7ff", "magenta": "#e0a0f0", "cyan": "#74d3de", "white": "#ffffff",
}


def _hex_for(color: str, bright: bool) -> str | None:
    """Map a pyte colour (name, or 6-digit hex for 256/true-colour) to #rrggbb."""
    if not color or color == "default":
        return None
    table = _ANSI_BRIGHT if bright else _ANSI
    if color in table:
        return table[color]
    if len(color) == 6 and all(c in "0123456789abcdefABCDEF" for c in color):
        return "#" + color
    return None


class TerminalView(QTextEdit):
    """Read-only, monospace, dark log view backed by a pyte terminal screen."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)
        self.setStyleSheet(f"QTextEdit {{ background: {_DEFAULT_BG}; color: {_DEFAULT_FG}; }}")

        self._screen = pyte.Screen(_COLS, _ROWS)
        # We feed raw program output (a bare "\n", since there's no TTY driver to
        # add the carriage return). LNM makes line-feed also return the carriage,
        # so lines start at column 0 instead of drifting right.
        self._screen.set_mode(pyte.modes.LNM)
        self._stream = pyte.Stream(self._screen)
        # The document grows to the content height (cursor high-water mark), so the
        # bottom is the live line and "stick to bottom" follows the output.
        self.setPlainText("")
        self._content_rows = 0

        self._dirty = False
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # --- public API ---------------------------------------------------------

    def clear_screen(self) -> None:
        self._screen.reset()
        self._screen.set_mode(pyte.modes.LNM)  # reset() drops modes; re-enable LF→newline
        self.setPlainText("")
        self._content_rows = 0
        self._dirty = True

    def feed(self, text: str) -> None:
        try:
            self._stream.feed(text)
        except Exception:
            pass  # never let a malformed escape sequence break the GUI
        self._dirty = True

    # --- rendering -----------------------------------------------------------

    def _tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self._render()

    def _render(self) -> None:
        bar = self.verticalScrollBar()
        stick_to_bottom = bar.value() >= bar.maximum() - 4
        doc = self.document()
        # Grow the document to the live content height (cursor high-water mark) so
        # the document's bottom is the live line, not trailing blank rows.
        self._content_rows = min(_ROWS, max(self._content_rows, self._screen.cursor.y + 1))
        if doc.blockCount() < self._content_rows:
            tail = QTextCursor(doc)
            tail.movePosition(QTextCursor.MoveOperation.End)
            tail.insertText("\n" * (self._content_rows - doc.blockCount()))

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        for y in sorted(self._screen.dirty):
            if y >= self._content_rows:
                continue  # a future (blank) row below the live content
            block = doc.findBlockByNumber(y)
            if not block.isValid():
                continue
            cursor.setPosition(block.position())
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            for text, fmt in self._row_runs(y):
                cursor.insertText(text, fmt)
        cursor.endEditBlock()
        self._screen.dirty.clear()
        if stick_to_bottom:
            bar.setValue(bar.maximum())

    def _row_runs(self, y: int) -> list[tuple[str, QTextCharFormat]]:
        row = self._screen.buffer[y]
        runs: list[tuple[tuple, str]] = []
        key = None
        chars: list[str] = []
        for x in range(self._screen.columns):
            ch = row[x]
            this = (ch.fg, ch.bg, ch.bold, ch.reverse)
            if this != key:
                if chars:
                    runs.append((key, "".join(chars)))
                chars = []
                key = this
            chars.append(ch.data or " ")
        if chars:
            runs.append((key, "".join(chars)))
        # Trim trailing default-styled spaces so lines aren't padded to 120 cols.
        while runs:
            k, txt = runs[-1]
            if not _is_plain(k):
                break
            stripped = txt.rstrip(" ")
            if stripped == txt:
                break
            if stripped:
                runs[-1] = (k, stripped)
                break
            runs.pop()
        return [(text, self._fmt(k)) for k, text in runs]

    def _fmt(self, key: tuple) -> QTextCharFormat:
        fg, bg, bold, reverse = key
        fg_hex = _hex_for(fg, bold)
        bg_hex = _hex_for(bg, False)
        if reverse:
            fg_hex, bg_hex = bg_hex or _DEFAULT_BG, fg_hex or _DEFAULT_FG
        fmt = QTextCharFormat()
        if fg_hex:
            fmt.setForeground(QColor(fg_hex))
        if bg_hex:
            fmt.setBackground(QColor(bg_hex))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt


def _is_plain(key: tuple) -> bool:
    fg, bg, bold, reverse = key
    return fg == "default" and bg == "default" and not bold and not reverse
