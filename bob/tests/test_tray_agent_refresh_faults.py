"""Executable fault injection for Get-BobTrayWorkerAgentChoices refresh.

Static source pins do not run the catch path. This drives the real function
with a Start-Process stand-in: a good first list, then a refresh that times
out, returns empty, returns the all-unknown placeholder, emits malformed JSON,
or throws. Each fault must leave the first rows unchanged. A real refresh
reading still replaces them.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import REPO

WATCH = REPO / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS, reason="needs powershell.exe or pwsh to execute the tray function")

FIRST = {
    "refresh": True,
    "agents": [
        {"id": "auto", "label": "Automatic", "available": True, "installed": True,
         "reason": "Grok, then Cursor, then OpenCode"},
        {"id": "grok", "label": "Grok", "available": True, "installed": True,
         "reason": "explicit grok (weekly pct=99)"},
        {"id": "cursor", "label": "Cursor", "available": False, "installed": False,
         "reason": "explicit cursor: agent.cmd missing"},
        {"id": "opencode", "label": "OpenCode", "available": False, "installed": True,
         "reason": "explicit opencode: no usable fuel (free=0 go=0)"},
    ],
}
UNKNOWN = {
    "refresh": False,
    "agents": [
        {"id": "auto", "label": "Automatic", "available": True, "installed": True,
         "reason": "Grok, then Cursor, then OpenCode"},
        {"id": "grok", "label": "Grok", "available": True, "installed": True,
         "reason": "fuel unknown (not exhausted); start checks this agent"},
        {"id": "cursor", "label": "Cursor", "available": True, "installed": True,
         "reason": "fuel unknown (not exhausted); start checks this agent"},
        {"id": "opencode", "label": "OpenCode", "available": True, "installed": True,
         "reason": "fuel unknown (not exhausted); start checks this agent"},
    ],
}
REAL = {
    "refresh": False,
    "agents": [
        {"id": "auto", "label": "Automatic", "available": True, "installed": True,
         "reason": "Grok, then Cursor, then OpenCode"},
        {"id": "grok", "label": "Grok", "available": True, "installed": True,
         "reason": "explicit grok (weekly pct=99)"},
        {"id": "cursor", "label": "Cursor", "available": False, "installed": False,
         "reason": "explicit cursor: agent.cmd missing"},
        {"id": "opencode", "label": "OpenCode", "available": True, "installed": True,
         "reason": "explicit opencode (free=100)"},
    ],
}


def _fn_source() -> str:
    text = WATCH.read_text(encoding="utf-8-sig")
    start = text.index("function Get-BobTrayWorkerAgentChoices {")
    end = text.index("function Update-BobTrayWorkerAgentsMenu {")
    return text[start:end]


def _rows(payload: dict) -> list[tuple]:
    return [
        (row["id"], bool(row["available"]), row["reason"])
        for row in payload["agents"]
    ]


def _run(tmp_path: Path, fault: str) -> list[tuple]:
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    script = tmp_path / "harness.ps1"
    script.write_text(_harness(fault), encoding="utf-8")
    proc = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **dict(**{k: v for k, v in __import__("os").environ.items()}),
            "BOB_TRAY_LIST_FAULT": fault,
            "BOB_TRAY_LIST_ROOT": str(root),
            "BOB_TRAY_LIST_FIRST": json.dumps(FIRST, separators=(",", ":")),
            "BOB_TRAY_LIST_UNKNOWN": json.dumps(UNKNOWN, separators=(",", ":")),
            "BOB_TRAY_LIST_REAL": json.dumps(REAL, separators=(",", ":")),
        },
    )
    assert proc.returncode == 0, (proc.stdout or "")[-800:] + (proc.stderr or "")[-800:]
    rows = []
    for line in (proc.stdout or "").splitlines():
        if not line.startswith("ROW\t"):
            continue
        _tag, ident, available, reason = line.split("\t", 3)
        rows.append((ident, available == "True", reason))
    assert rows, proc.stdout
    return rows


def _harness(fault: str) -> str:
    fn = _fn_source()
    return r"""
$ErrorActionPreference = 'Stop'
$RepoRoot = $env:BOB_TRAY_LIST_ROOT
function Start-Process {
    [CmdletBinding()]
    param(
        [string]$FilePath,
        $ArgumentList,
        [switch]$PassThru,
        [string]$WindowStyle,
        [string]$RedirectStandardOutput,
        [string]$RedirectStandardError
    )
    $refresh = $false
    foreach ($a in @($ArgumentList)) { if ([string]$a -eq '--refresh-fuel') { $refresh = $true } }
    if ($refresh -and $env:BOB_TRAY_LIST_FAULT -eq 'throw') { throw 'start failed' }
    $body = ''
    $timedOut = $false
    if (-not $refresh) { $body = $env:BOB_TRAY_LIST_FIRST }
    elseif ($env:BOB_TRAY_LIST_FAULT -eq 'timeout') { $timedOut = $true }
    elseif ($env:BOB_TRAY_LIST_FAULT -eq 'empty') { $body = '' }
    elseif ($env:BOB_TRAY_LIST_FAULT -eq 'unknown') { $body = $env:BOB_TRAY_LIST_UNKNOWN }
    elseif ($env:BOB_TRAY_LIST_FAULT -eq 'malformed') { $body = '{not-json' }
    elseif ($env:BOB_TRAY_LIST_FAULT -eq 'real') { $body = $env:BOB_TRAY_LIST_REAL }
    else { throw ('bad fault ' + $env:BOB_TRAY_LIST_FAULT) }
    if ($RedirectStandardOutput) {
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [IO.File]::WriteAllText($RedirectStandardOutput, [string]$body, $utf8)
    }
    $holder = New-Object psobject -Property @{ TimedOut = $timedOut }
    $holder | Add-Member -MemberType ScriptMethod -Name WaitForExit -Value {
        param($ms)
        return -not $this.TimedOut
    }
    $holder | Add-Member -MemberType ScriptMethod -Name Kill -Value { }
    $holder | Add-Member -MemberType ScriptMethod -Name Dispose -Value { }
    return $holder
}
""" + fn + r"""
$rows = @(Get-BobTrayWorkerAgentChoices -InstallRoot $env:BOB_TRAY_LIST_ROOT)
foreach ($row in $rows) {
    $flag = 'False'
    if ($row.available) { $flag = 'True' }
    Write-Output ('ROW' + "`t" + [string]$row.id + "`t" + $flag + "`t" + [string]$row.reason)
}
exit 0
"""


@needs_ps
@pytest.mark.parametrize("fault", ["timeout", "empty", "unknown", "malformed", "throw"])
def test_refresh_fault_keeps_exact_first_rows(tmp_path: Path, fault: str):
    assert _run(tmp_path, fault) == _rows(FIRST)


@needs_ps
def test_refresh_real_reading_replaces_first_rows(tmp_path: Path):
    assert _run(tmp_path, "real") == _rows(REAL)


def test_harness_uses_the_repo_function():
    """The executable harness is the function in Watch-BobTray.ps1, not a copy."""
    src = _fn_source()
    assert "function Get-BobTrayWorkerAgentChoices {" in src
    assert "catch {" in src
    assert "if ($Refresh) { return $null }" in src
    assert "return $fallback" in src
