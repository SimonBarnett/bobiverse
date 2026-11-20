"""FR #8517: tray startworker accepts ISO expires and always writes res-*.json."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY_TOOLS = ROOT / "third_party" / "bob-tray" / "tools"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="tray PowerShell")


def _ps(tmp_path: Path, body: str, timeout: int = 90) -> str:
    f = tmp_path / "t.ps1"
    f.write_text(body, encoding="utf-8-sig")
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(f)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return (r.stdout or "") + (r.stderr or "")


@WIN
def test_iso_expires_launches_and_writes_res(tmp_path: Path):
    qd = tmp_path / "root" / "run" / "startworker"
    qd.mkdir(parents=True)
    exp = (datetime.now(timezone.utc) + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (qd / "req-iso.json").write_text(
        json.dumps(
            {
                "id": "iso",
                "mode": "agent",
                "by": "ops",
                "kind": "owner",
                "ts": exp,
                "expires": exp,
                "agent": "grok",
            }
        ),
        encoding="utf-8",
    )
    out = _ps(
        tmp_path,
        r'''
. "%s"
function Get-BobTrayWorkerCapRefusal { param([object[]]$Procs = $null, [string]$Mode = 'agent') '' }
function Test-BobTraySeatsOff { $false }
$dir = Get-BobTrayStartWorkerDir -Root "%s"
$global:launched = New-Object System.Collections.Generic.List[string]
$r = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch {
    param($m, $a)
    $global:launched.Add(("$m|$a"))
    5151
})
$r | ForEach-Object { 'ROW=' + $_.id + '|' + $_.ok + '|' + $_.reason + '|' + $_.pid }
"LAUNCHED=" + ($global:launched -join ',')
"RES=" + (Get-Content (Join-Path $dir 'res-iso.json') -Raw)
"REQLEFT=" + @(Get-ChildItem $dir -Filter 'req-*.json').Count
'''
        % (TRAY_TOOLS / "BobTrayStartWorker.ps1", tmp_path / "root"),
    )
    assert "ROW=iso|True|" in out and "|5151" in out
    assert "LAUNCHED=agent|grok" in out
    assert '"ok":true' in out and '"pid":5151' in out
    assert "REQLEFT=0" in out


@WIN
def test_garbage_expires_writes_bad_expires_res(tmp_path: Path):
    qd = tmp_path / "root" / "run" / "startworker"
    qd.mkdir(parents=True)
    fut = int(time.time()) + 600
    (qd / "req-bad.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "mode": "agent",
                "by": "ops",
                "kind": "owner",
                "ts": fut,
                "expires": "not-a-time",
            }
        ),
        encoding="utf-8",
    )
    (qd / "req-ok.json").write_text(
        json.dumps(
            {
                "id": "ok",
                "mode": "plan",
                "by": "ops",
                "kind": "owner",
                "ts": fut,
                "expires": fut,
            }
        ),
        encoding="utf-8",
    )
    out = _ps(
        tmp_path,
        r'''
. "%s"
function Get-BobTrayWorkerCapRefusal { param([object[]]$Procs = $null, [string]$Mode = 'agent') '' }
function Test-BobTraySeatsOff { $false }
$dir = Get-BobTrayStartWorkerDir -Root "%s"
$global:n = 0
$r = @(Invoke-BobTrayStartWorkerQueue -Dir $dir -Launch { param($m) $global:n++; 4242 })
$r | ForEach-Object { 'ROW=' + $_.id + '|' + $_.ok + '|' + $_.reason }
"LAUNCH_CALLS=" + $global:n
"RESBAD=" + (Test-Path (Join-Path $dir 'res-bad.json'))
"RESOK=" + (Get-Content (Join-Path $dir 'res-ok.json') -Raw)
'''
        % (TRAY_TOOLS / "BobTrayStartWorker.ps1", tmp_path / "root"),
    )
    assert "ROW=bad|False|bad-expires" in out
    assert "ROW=ok|True|" in out
    assert "LAUNCH_CALLS=1" in out
    assert "RESBAD=True" in out
    assert '"ok":true' in out


def test_helper_and_contract_present_in_source():
    src = (TRAY_TOOLS / "BobTrayStartWorker.ps1").read_text(encoding="utf-8")
    assert "function ConvertTo-BobTrayStartWorkerExpires" in src
    assert "bad-expires" in src
    assert "FR #8517" in src
    assert "FromUnixTimeSeconds" in src
    assert "DateTimeOffset]::Parse" in src or "[DateTimeOffset]::Parse" in src
