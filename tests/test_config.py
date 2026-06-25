"""Tests for the QSettings-backed GUI preferences (round-trips only)."""

from __future__ import annotations

from pathlib import Path

from pixiline import config


def test_parallel_enabled_defaults_false_and_round_trips(temp_settings):
    assert config.load_parallel_enabled() is False
    config.save_parallel_enabled(True)
    assert config.load_parallel_enabled() is True
    config.save_parallel_enabled(False)
    assert config.load_parallel_enabled() is False


def test_output_base_defaults_none_and_round_trips(temp_settings, tmp_path):
    assert config.load_output_base() is None
    config.save_output_base(tmp_path)
    assert config.load_output_base() == tmp_path


def test_recent_pipelines_defaults_empty_and_round_trips(temp_settings):
    assert config.load_recent_pipelines() == []
    roots = [Path("/a/one"), Path("/b/two")]
    config.save_recent_pipelines(roots)
    assert config.load_recent_pipelines() == roots


def test_recent_pipelines_drops_empty_entries(temp_settings):
    config.save_recent_pipelines([Path("/a/one")])
    # Simulate a stray empty value sneaking into the stored list.
    from PySide6.QtCore import QSettings

    QSettings().setValue("pipelines/recent", ["", "/a/one"])
    assert config.load_recent_pipelines() == [Path("/a/one")]
