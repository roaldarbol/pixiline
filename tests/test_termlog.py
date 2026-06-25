"""Tests for SettledLog: collapsing carriage-return progress + stripping ANSI."""

from __future__ import annotations

from pixiline.jobs.termlog import SettledLog


def settle(tmp_path, text: str) -> str:
    path = tmp_path / "log.txt"
    log = SettledLog(path)
    log.feed(text)
    log.close()
    return path.read_text(encoding="utf-8")


def test_plain_lines_are_rstripped_with_trailing_newline(tmp_path):
    assert settle(tmp_path, "hello   \nworld\n") == "hello\nworld\n"


def test_carriage_return_overwrites_in_place(tmp_path):
    # "20%" then a longer "100%" redraw on the same line -> only the final value.
    assert settle(tmp_path, "20%\r100%\n") == "100%\n"


def test_progress_spam_settles_to_final_value(tmp_path):
    assert settle(tmp_path, "10%\r40%\r100%\n") == "100%\n"


def test_ansi_colour_is_stripped(tmp_path):
    assert settle(tmp_path, "\x1b[31mred\x1b[0m\n") == "red\n"


def test_erase_in_line_clears_tail(tmp_path):
    # write "abcdef", move cursor to col 3 (CSI 4G), erase to end (CSI 0K).
    assert settle(tmp_path, "abcdef\x1b[4G\x1b[0K\n") == "abc\n"


def test_tab_expands_to_next_stop(tmp_path):
    assert settle(tmp_path, "ab\tc\n") == "ab      c\n"


def test_backspace_moves_cursor_back(tmp_path):
    assert settle(tmp_path, "abc\b\bX\n") == "aXc\n"


def test_erase_whole_line(tmp_path):
    assert settle(tmp_path, "abcdef\x1b[2K\n") == "\n"


def test_erase_to_cursor_pads_with_spaces(tmp_path):
    # cursor to col 3 (CSI 4G), erase-to-cursor (CSI 1K) -> leading run blanked.
    assert settle(tmp_path, "abcdef\x1b[4G\x1b[1K\n") == "   def\n"


def test_lone_escape_is_dropped(tmp_path):
    assert settle(tmp_path, "a\x1bb\n") == "ab\n"


def test_close_flushes_unterminated_final_line(tmp_path):
    assert settle(tmp_path, "no newline here") == "no newline here\n"


def test_logging_is_best_effort_when_path_unwritable(tmp_path):
    # An ancestor that is a file makes mkdir fail; the log must swallow it.
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    path = blocker / "sub" / "log.txt"
    log = SettledLog(path)
    log.feed("anything\n")  # no-op, must not raise
    log.close()
    assert not path.exists()
