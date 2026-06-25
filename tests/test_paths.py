"""Tests for locating the pixi launcher."""

from __future__ import annotations

from pixiline import paths


def test_pixi_exe_prefers_env_override(monkeypatch):
    monkeypatch.setenv("PIXI_EXE", "/custom/pixi")
    assert paths.pixi_executable() == "/custom/pixi"


def test_pixi_exe_uses_path_when_no_override(monkeypatch):
    monkeypatch.delenv("PIXI_EXE", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: "/usr/bin/pixi")
    assert paths.pixi_executable() == "/usr/bin/pixi"


def test_pixi_exe_falls_back_to_home_install(monkeypatch, tmp_path):
    monkeypatch.delenv("PIXI_EXE", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    bindir = tmp_path / ".pixi" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "pixi").write_text("#!/bin/sh\n")
    assert paths.pixi_executable() == str(bindir / "pixi")


def test_pixi_exe_falls_back_to_bare_name(monkeypatch, tmp_path):
    monkeypatch.delenv("PIXI_EXE", raising=False)
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    monkeypatch.setattr(paths.Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.pixi_executable() == "pixi"
