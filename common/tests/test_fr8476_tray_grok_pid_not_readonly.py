"""FR #8476: tray code must not assign the read-only automatic ``$PID``.

Windows PowerShell 5.1 rejects ``$pid = ...`` with
"Cannot overwrite variable PID because it is read-only or constant".
That broke Get-BobLiveGrokAgents (live grok row never recorded the pid)
and the same pattern sat in the digest pool and git-accept helpers.
"""
from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_no_readonly_pid_assignment_in_tray_sources():
    for rel in (
        "bob/tray/src/Public/Get-BobTrayHover.ps1",
        "bob/tray/src/Private/Invoke-BobGitAccept.ps1",
    ):
        text = _src(rel)
        assert not re.search(r"(?im)^\s*\$pid\s*=", text), f"read-only $pid assignment left in {rel}"


def test_live_grok_agents_uses_proc_id():
    text = _src("bob/tray/src/Public/Get-BobTrayHover.ps1")
    start = text.index("function Get-BobLiveGrokAgents")
    end = text.index("function ", start + len("function Get-BobLiveGrokAgents"))
    body = text[start:end]
    assert "$procId = [int]$p.ProcessId" in body
    assert "if ($byPid.ContainsKey($procId))" in body
    assert "('grok-' + $procId)" in body
    assert "pid        = $procId" in body
