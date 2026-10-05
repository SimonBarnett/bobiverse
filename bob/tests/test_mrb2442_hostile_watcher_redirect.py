"""MRB #2442 hostile: Build-BobWatcher must not redirect stdout+stderr to the same path."""
from __future__ import annotations

import re
from pathlib import Path

from repo_layout import ROOT

WATCHER = ROOT / "bob/scripts/Build-BobWatcher.ps1"
WORKER = ROOT / "bob/scripts/Build-BobWorker.ps1"
JEEVES = ROOT / "jeeves/scripts/Build-Jeeves.ps1"


def _redirect_pair(line: str) -> tuple[str, str] | None:
    m = re.search(
        r"RedirectStandardOutput\s+(\S+)\s+-RedirectStandardError\s+(\S+)",
        line,
    )
    if not m:
        return None
    return m.group(1).rstrip("`"), m.group(2).rstrip("`")


def test_mrb2442_watcher_uses_distinct_stdout_stderr_logs():
    text = WATCHER.read_text(encoding="utf-8-sig")
    assert "pyinstaller.stdout.log" in text
    assert "pyinstaller.stderr.log" in text
    assert "RedirectStandardOutput $stdout" in text
    assert "RedirectStandardError $stderr" in text
    # Must not assign both redirects to the same variable/path expression.
    for i, line in enumerate(text.splitlines(), 1):
        pair = _redirect_pair(line)
        if pair:
            assert pair[0] != pair[1], f"same redirect path at line {i}: {line}"


def test_mrb2442_sibling_builders_also_use_distinct_logs():
    for path in (WORKER, JEEVES):
        text = path.read_text(encoding="utf-8-sig")
        assert "pyinstaller.stdout.log" in text, path.name
        assert "pyinstaller.stderr.log" in text, path.name
        for i, line in enumerate(text.splitlines(), 1):
            pair = _redirect_pair(line)
            if pair:
                assert pair[0] != pair[1], f"{path.name}:{i}: {line}"


def test_mrb2442_watcher_failure_prints_both_logs():
    text = WATCHER.read_text(encoding="utf-8-sig")
    assert "--- stdout ---" in text and "--- stderr ---" in text
    assert "watcher build failed" in text


def test_mrb2442_encoding_utf8():
    raw = WATCHER.read_bytes()
    # PowerShell scripts may carry UTF-8 BOM; content must decode.
    text = raw.decode("utf-8-sig")
    assert "Start-Process" in text
    assert not re.search(
        r"RedirectStandardOutput\s+(\$\w+)\s+-RedirectStandardError\s+\1\b",
        text,
    )
