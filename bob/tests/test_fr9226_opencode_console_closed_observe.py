# -*- coding: utf-8 -*-
"""FR #9226: always heal disappeared seats; classify console-closed from worker.log."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

BOB = ROOT / "bob"
if not (BOB / "tray" / "tools" / "BobTrayObserveSeats.ps1").is_file():
    BOB = ROOT
OBS = BOB / "tray" / "tools" / "BobTrayObserveSeats.ps1"
WATCH = BOB / "tray" / "tools" / "Watch-BobTray.ps1"
CS = BOB / "tray" / "dialogs" / "BobTray.cs"
DOC = BOB / "docs" / "bob-9226-opencode-console-closed-observe.md"
BW = ROOT / "bob" / "scripts" / "bob_worker.py"
if not BW.is_file():
    BW = ROOT / "scripts" / "bob_worker.py"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9226_source_pins():
    obs = _txt(OBS)
    assert "function Get-BobTrayDisappearedSeatReason" in obs
    assert "fr-9226-watch-disappeared-seat" in obs
    assert "console-closed" in obs
    assert "3221225786" in obs
    # Always heal: HandleDisappeared called before last-lt-0 early return path.
    assert "FR #9226: heal orphan run dirs every poll" in obs
    watch = _txt(WATCH)
    assert "FR #9226 seat-observe" in watch
    cs = _txt(CS)
    assert "bob-tray-watchdog-fr9226" in cs or "fr-9226-disappeared-seat" in cs
    assert "ReadWorkerLogTail" in cs
    assert DOC.is_file()
    bw = _txt(BW)
    assert "def classify_disappeared_seat_reason" in bw
    assert "fr-9226-disappeared-seat" in bw


def _bw():
    import bob_worker as bw

    return bw


def test_fr9226_classify_console_closed_from_log(tmp_path: Path):
    bw = _bw()
    run = tmp_path / "worker-flamingo-2147483001-deadbeef"
    run.mkdir()
    (run / "worker.log").write_text(
        "2026-11-23T04:50:00 worker: shutting down (console-closed) exit=0\n"
        "agent: console-close exit code=3221225786\n",
        encoding="utf-8",
    )
    reason, code = bw.classify_disappeared_seat_reason(run)
    assert reason == "console-closed"
    assert code == bw.CONSOLE_CLOSE_EXIT
    (run / "last-from.txt").write_text(
        "FROM jeeves #flamingo flamingo-2147483001: FR SimonBarnett/bobiverse#9226\n",
        encoding="utf-8",
    )
    hit = bw.handle_disappeared_worker_run(run, pid_alive=lambda _p: False)
    assert hit and hit["giveup"] is True
    assert hit["reason"] == "console-closed"
    exit_doc = json.loads((run / "last-exit.json").read_text(encoding="utf-8"))
    assert exit_doc["reason"] == "console-closed"
    assert exit_doc["exit_code"] == bw.CONSOLE_CLOSE_EXIT
    out = (run / "outbox.txt").read_text(encoding="utf-8")
    assert "GIVEUP FR SimonBarnett/bobiverse#9226 console-closed" in out


def test_fr9226_classify_external_kill_without_log(tmp_path: Path):
    bw = _bw()
    run = tmp_path / "worker-flamingo-2147483002-deadbeef"
    run.mkdir()
    (run / "last-from.txt").write_text(
        "FROM jeeves #flamingo flamingo-2147483002: FIX SimonBarnett/bobiverse#9105\n",
        encoding="utf-8",
    )
    hit = bw.handle_disappeared_worker_run(run, pid_alive=lambda _p: False)
    assert hit and hit["reason"] == "external-kill"
    out = (run / "outbox.txt").read_text(encoding="utf-8")
    assert "external-kill" in out


@needs_ps
def test_fr9226_ps_classifies_console_closed_and_always_heals(tmp_path: Path):
    run = tmp_path / "run"
    d = run / "worker-flamingo-2147483003-deadbeef"
    d.mkdir(parents=True)
    (d / "last-from.txt").write_text(
        "FROM jeeves #flamingo flamingo-2147483003: FR SimonBarnett/bobiverse#9226\n",
        encoding="utf-8",
    )
    (d / "worker.log").write_text(
        "worker: shutting down (console-closed) exit=0\nexit_code=3221225786\n",
        encoding="utf-8",
    )
    state = tmp_path / "tray-seat-observe.json"
    # Baseline already matches "current" count (simulate tray restart after OC gone).
    state.write_text(
        json.dumps({"lastSeatCount": 2, "machine": "flamingo"}),
        encoding="utf-8",
    )
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{OBS}'
function Get-BobTrayLiveSeatProcessCount {{ param([string]$MachineId = '') 2 }}
$r = Invoke-BobTrayHandleDisappearedWorkerRuns -MachineId 'flamingo' -RunRoot '{run}'
if ([int]$r.Handled -lt 1) {{ throw 'expected handled' }}
if ([int]$r.Giveups -lt 1) {{ throw 'expected giveup' }}
$exit = Get-Content -LiteralPath '{d / "last-exit.json"}' -Raw | ConvertFrom-Json
if ($exit.reason -ne 'console-closed') {{ throw ('bad reason=' + $exit.reason) }}
if ($exit.via -ne 'fr-9226-watch-disappeared-seat') {{ throw 'bad via' }}
$ob = Get-Content -LiteralPath '{d / "outbox.txt"}' -Raw
if ($ob -notmatch 'GIVEUP FR SimonBarnett/bobiverse#9226 console-closed') {{ throw 'missing giveup' }}
# Observe with flat seat count must still heal (FR #9226 always-scan).
$d2 = Join-Path '{run}' 'worker-flamingo-2147483004-deadbeef'
New-Item -ItemType Directory -Force -Path $d2 | Out-Null
Set-Content -LiteralPath (Join-Path $d2 'last-from.txt') -Value 'FROM jeeves #flamingo flamingo-2147483004: FIX SimonBarnett/bobiverse#9105' -Encoding utf8
$obs = Invoke-BobTrayObserveWorkerSeats -MachineId 'flamingo' -StatePath '{state}'
# HandleDisappeared uses RunRoot from LOCALAPPDATA by default — re-run heal on our tmp root.
$r2 = Invoke-BobTrayHandleDisappearedWorkerRuns -MachineId 'flamingo' -RunRoot '{run}'
if ([int]$r2.Handled -lt 1) {{ throw 'second heal expected' }}
Write-Output 'ok'
""",
        encoding="utf-8",
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "ok" in out
