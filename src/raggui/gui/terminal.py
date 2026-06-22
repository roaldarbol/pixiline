"""A small terminal-emulator log view.

Program output is fed through a pyte screen, so carriage returns / cursor moves
update the log *in place* (a progress bar stays one refreshing line instead of
scrolling thousands of lines) and ANSI colour codes render as real colours. Only
the screen lines pyte marks dirty are repainted, and on a throttle, so it stays
cheap even for very chatty, hours-long runs. Colours follow the app's light/dark
theme.
"""

from __future__ import annotations

import pyte
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit

from raggui import applog
from raggui.gui.theme import is_dark, watch_app_palette

_COLS, _ROWS = 120, 300        # terminal size (rows = how much scrollback is kept)
_REFRESH_MS = 80               # repaint at most ~12x/sec

# A palette per mode: background, default text, and the 16 ANSI colours (normal +
# bright). The light set uses darker, saturated hues that read on a light field;
# the dark set uses the brighter ones that read on a dark field.
_DARK = {
    "bg": "#1e1e1e",
    "fg": "#d4d4d4",
    "ansi": {
        "black": "#5c6370", "red": "#e06c75", "green": "#98c379", "brown": "#d19a66",
        "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#abb2bf",
    },
    "ansi_bright": {
        "black": "#7f8696", "red": "#ff7b86", "green": "#b5e890", "brown": "#e5c07b",
        "blue": "#7cc7ff", "magenta": "#e0a0f0", "cyan": "#74d3de", "white": "#ffffff",
    },
}
_LIGHT = {
    "bg": "#ffffff",
    "fg": "#1f2328",
    "ansi": {
        "black": "#24292f", "red": "#cf222e", "green": "#1a7f37", "brown": "#9a6700",
        "blue": "#0969da", "magenta": "#8250df", "cyan": "#1b7c83", "white": "#6e7781",
    },
    "ansi_bright": {
        "black": "#6e7781", "red": "#cf222e", "green": "#1a7f37", "brown": "#bc4c00",
        "blue": "#0969da", "magenta": "#8250df", "cyan": "#1b7c83", "white": "#24292f",
    },
}


class TerminalView(QTextEdit):
    """Read-only, monospace, theme-aware log view backed by a pyte terminal screen."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)

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

        self._pal = _DARK
        self._apply_theme()
        watch_app_palette(self, self._apply_theme)

        self._dirty = False
        self._render_errored = False
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

    # --- sizing --------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._fit_columns()

    def _fit_columns(self) -> None:
        """Resize the terminal to as many columns as fit the current width, like a
        real terminal. pyte then wraps output to that width, so it always fills the
        pane and re-flows on resize."""
        try:
            # Average over many chars so the fractional cell width is accurate (a
            # single-char advance rounds and accumulates into an overflowing line).
            char_w = self.fontMetrics().horizontalAdvance("M" * 100) / 100.0 or 8.0
            margin = 2 * self.document().documentMargin()  # the text's left + right inset
            avail = max(0.0, self.viewport().width() - margin)
            cols = max(20, int(avail / char_w) - 1)  # -1 column of safety so nothing clips
            if cols == self._screen.columns:
                return
            # pyte preserves the buffer across resize, so just repaint the existing
            # rows at the new width (no document clear — that would blank the view).
            self._screen.resize(_ROWS, cols)
            self._screen.dirty.update(range(min(self._content_rows + 1, _ROWS)))
            self._dirty = True
        except Exception:
            self._note_error("terminal resize failed")

    # --- theming -------------------------------------------------------------

    def _apply_theme(self) -> None:
        self._pal = _DARK if is_dark() else _LIGHT
        self.setStyleSheet(
            f"QTextEdit {{ background: {self._pal['bg']}; color: {self._pal['fg']}; }}"
        )
        # Repaint existing content with the new palette (colours are baked into the
        # document's char formats, so a stylesheet change alone wouldn't recolour).
        if self._content_rows:
            self._screen.dirty.update(range(self._content_rows))
            self._render()

    def _hex_for(self, color: str, bright: bool) -> str | None:
        """Map a pyte colour (name, or 6-digit hex for 256/true-colour) to #rrggbb."""
        if not color or color == "default":
            return None
        table = self._pal["ansi_bright"] if bright else self._pal["ansi"]
        if color in table:
            return table[color]
        if len(color) == 6 and all(c in "0123456789abcdefABCDEF" for c in color):
            return "#" + color
        return None

    # --- rendering -----------------------------------------------------------

    def _tick(self) -> None:
        if self._dirty:
            self._dirty = False
            self._render()

    def _render(self) -> None:
        # A render error must never abort the GUI (PySide aborts on an unhandled
        # exception in a slot), so catch everything and keep going.
        try:
            self._do_render()
        except Exception:
            self._note_error("terminal render failed")

    def _note_error(self, what: str) -> None:
        """Log a render/resize failure once (avoid spamming a recurring one)."""
        if not self._render_errored:
            self._render_errored = True
            applog.log.exception(what)

    def _do_render(self) -> None:
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
        fg_hex = self._hex_for(fg, bold)
        bg_hex = self._hex_for(bg, False)
        if reverse:
            fg_hex, bg_hex = bg_hex or self._pal["bg"], fg_hex or self._pal["fg"]
        fmt = QTextCharFormat()
        # Always set an explicit foreground: a default cell must use the theme's
        # text colour, not the document default (black), or it vanishes in dark mode.
        fmt.setForeground(QColor(fg_hex or self._pal["fg"]))
        if bg_hex:
            fmt.setBackground(QColor(bg_hex))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt


def _is_plain(key: tuple) -> bool:
    fg, bg, bold, reverse = key
    return fg == "default" and bg == "default" and not bold and not reverse
