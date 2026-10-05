"""FR #2441 / verify #2443: Build-BobWatcher must use separate stdout/stderr redirect paths."""
from __future__ import annotations

from repo_layout import ROOT

SCRIPT = ROOT / "bob" / "scripts" / "Build-BobWatcher.ps1"


def test_build_bob_watcher_separate_stdout_stderr_logs():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "pyinstaller.stdout.log" in text
    assert "pyinstaller.stderr.log" in text
    assert "-RedirectStandardOutput $stdout" in text
    assert "-RedirectStandardError $stderr" in text
    assert "-RedirectStandardOutput $stderr" not in text
    assert "-RedirectStandardError $stdout" not in text


def test_stdout_and_stderr_log_paths_differ():
    text = SCRIPT.read_text(encoding="utf-8-sig")
    assert "pyinstaller.stdout.log" in text and "pyinstaller.stderr.log" in text
    assert text.index("pyinstaller.stdout.log") != text.index("pyinstaller.stderr.log")
