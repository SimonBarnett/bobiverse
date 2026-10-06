"""Hostile MRB #2733 / FR #2728: !status uptime, frozen VERSION, digest busy."""
from __future__ import annotations

import inspect
import time
from pathlib import Path

import chair_commands as cc
import irc_agent


def test_mrb2733_client_init_sets_process_started():
    src = inspect.getsource(irc_agent.Client.__init__)
    assert "_process_started" in src
    assert "time.time()" in src


def test_mrb2733_queue_line_keeps_accepted_separate_from_busy(tmp_path):
    """accepted= stays on queue:; busy= must not be aliased to accepted count."""
    lines = cc.status_lines(tmp_path, started=time.time() - 5, now=time.time(), version="x")
    assert lines[1].startswith("queue:")
    assert "accepted=" in lines[1]
    assert lines[2].startswith("workers: busy=")
    # busy line is only the busy count (no accepted= smuggled onto workers:)
    assert "accepted=" not in lines[2]


def test_mrb2733_resolve_install_root_from_frozen_jeeves_exe(tmp_path):
    root = tmp_path / "ai"
    exe = root / "jeeves" / "jeeves.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    got = cc.resolve_jeeves_install_root(
        env={},
        frozen=True,
        executable=exe,
        file_path=tmp_path / "_MEI" / "chair_commands.pyc",
    )
    assert got == root.resolve()


def test_mrb2733_build_jeeves_bundles_version():
    script = Path(__file__).resolve().parents[1] / "scripts" / "Build-Jeeves.ps1"
    text = script.read_text(encoding="utf-8")
    assert "FR #2728" in text
    assert "--add-data" in text
    assert "VERSION" in text


def test_mrb2733_read_version_never_question_mark_when_install_has_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BOBIVERSE_VERSION", raising=False)
    monkeypatch.delenv("BOB_VERSION", raising=False)
    monkeypatch.delenv("JEEVES_VERSION", raising=False)
    install = tmp_path / "jeeves-root"
    install.mkdir()
    (install / "VERSION").write_text("7.7.7\n", encoding="utf-8")
    mei = tmp_path / "mei"
    mei.mkdir()
    got = cc.read_version(
        env={"JEEVES_INSTALL_ROOT": str(install)},
        frozen=True,
        meipass=mei,
        executable=tmp_path / "x" / "jeeves.exe",
    )
    assert got == "7.7.7"
    assert got != "?"
