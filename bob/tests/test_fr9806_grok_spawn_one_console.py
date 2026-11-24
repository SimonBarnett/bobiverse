"""FR #9806: .NET Grok spawn always-new, one console (assert_fresh + inherit).

Pins AssertFresh / GrokSpawn / StartupProgress.Stop-before-spawn, workflow
--selftest-spawn smoke, and docs. Airc no-SDK does not apply (net8 SDK).
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WF = ROOT / ".github" / "workflows" / "build-bob-worker-net.yml"
DOTNET = ROOT / "bob" / "worker" / "dotnet"
ASSERT = DOTNET / "AssertFresh.cs"
SPAWN = DOTNET / "GrokSpawn.cs"
PROGRESS = DOTNET / "StartupProgress.cs"
PROGRAM = DOTNET / "Program.cs"
DOCS = ROOT / "bob" / "docs" / "bob-worker-net.md"


def _t(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fr9806_assert_fresh_source_pins():
    assert ASSERT.is_file(), "missing AssertFresh.cs"
    text = _t(ASSERT)
    assert "ForbiddenFlags" in text
    for flag in ("--resume", "-r", "--continue", "-c", "--resume-session", "--session", "--chat"):
        assert flag in text
    assert "refusing to launch" in text
    assert "InvalidOperationException" in text


def test_fr9806_grok_spawn_inherits_console_no_new_console():
    assert SPAWN.is_file(), "missing GrokSpawn.cs"
    text = _t(SPAWN)
    assert "CREATE_NEW_CONSOLE" in text
    assert "creationFlags = 0" in text or "creationFlags=0" in text or "const uint creationFlags = 0" in text
    assert "AssertFresh.Assert" in text
    assert "progress?.Stop()" in text or "progress.Stop()" in text
    assert "UseShellExecute = false" in text
    assert "RedirectStandardInput = false" in text
    assert "CreateNoWindow = false" in text
    assert "-s" in text  # new session flag, not --resume
    assert "--no-auto-update" in text


def test_fr9806_startup_progress_stop_before_spawn():
    assert PROGRESS.is_file()
    text = _t(PROGRESS)
    assert "Stop()" in text
    assert "BOB_WORKER_STARTUP_PROGRESS" in text
    prog = _t(PROGRAM)
    assert "--selftest-spawn" in prog
    assert "RunSelftestSpawn" in prog
    assert "spinner_stopped" in prog or "stopped_spinner" in prog
    assert "InheritConsoleSmoke" in prog or "creation_flags" in prog


def test_fr9806_ci_runs_selftest_spawn():
    assert WF.is_file()
    text = _t(WF)
    assert "--selftest-spawn" in text
    assert "test_fr9806_grok_spawn_one_console.py" in text
    assert "fr_spawn=9806" in text or "9806" in text
    assert "setup-dotnet@v4" in text


def test_fr9806_docs_cover_assert_fresh_and_one_console():
    docs = _t(DOCS)
    assert "FR #9806" in docs
    assert "assert_fresh" in docs or "AssertFresh" in docs
    assert "CREATE_NEW_CONSOLE" in docs or "one console" in docs.lower() or "inherit" in docs.lower()
    assert "--selftest-spawn" in docs
    assert "no-SDK" in docs or "no-SDK" in docs.replace(" ", "")
