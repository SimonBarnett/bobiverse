# -*- coding: utf-8 -*-
"""FR #9208: Watch observe seat drops + monitor under-count for redqueen OpenCode."""
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
OC = ROOT / "jeeves" / "tools" / "monitor" / "opencode_seats.py"
DOC = BOB / "docs" / "bob-9208-digest-clear-on-seat-exit.md"
PS = shutil.which("powershell.exe") or shutil.which("powershell")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    assert p.is_file(), p
    return p.read_text(encoding="utf-8-sig")


def test_fr9208_source_pins():
    obs = _txt(OBS)
    assert "function Invoke-BobTrayObserveWorkerSeats" in obs
    assert "function Invoke-BobTrayHandleDisappearedWorkerRuns" in obs
    assert "FR #9208" in obs
    assert "GIVEUP" in obs
    assert "external-kill" in obs
    watch = _txt(WATCH)
    assert "BobTrayObserveSeats.ps1" in watch
    assert "Invoke-BobTrayObserveWorkerSeats" in watch
    assert "FR #9208" in watch
    oc = _txt(OC)
    assert "redqueen" in oc
    assert "def expect_seats" in oc
    assert "under-count" in oc or "under_count" in oc
    assert DOC.is_file()


@needs_ps
def test_fr9208_disappeared_run_writes_giveup(tmp_path: Path):
    run = tmp_path / "run"
    d = run / "worker-redqueen-2147483000-deadbeef"
    d.mkdir(parents=True)
    (d / "last-from.txt").write_text(
        "FROM jeeves #redqueen redqueen-2147483000: FIX SimonBarnett/bobiverse#9105\n",
        encoding="utf-8",
    )
    script = tmp_path / "run.ps1"
    script.write_text(
        f"""
$ErrorActionPreference = 'Stop'
. '{OBS}'
$r = Invoke-BobTrayHandleDisappearedWorkerRuns -MachineId 'redqueen' -RunRoot '{run}'
if ([int]$r.Handled -lt 1) {{ throw 'expected handled' }}
if ([int]$r.Giveups -lt 1) {{ throw 'expected giveup' }}
$exit = Get-Content -LiteralPath '{d / "last-exit.json"}' -Raw | ConvertFrom-Json
if ($exit.via -ne 'fr-9208-watch-disappeared-seat') {{ throw 'bad via' }}
$ob = Get-Content -LiteralPath '{d / "outbox.txt"}' -Raw
if ($ob -notmatch 'GIVEUP FIX SimonBarnett/bobiverse#9105') {{ throw 'missing giveup' }}
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


def test_fr9208_monitor_undercount_redqueen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import importlib.util
    import sys

    mon = OC.parent
    if str(mon) not in sys.path:
        sys.path.insert(0, str(mon))
    spec = importlib.util.spec_from_file_location("opencode_seats_9208", OC)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fixture = {
        "machines": {
            "redqueen": {
                "online": True,
                "worker_list": [
                    {
                        "nick": "redqueen-10204",
                        "machine": "redqueen",
                        "state": "offered",
                        "kind": "opencode",
                        "work": "FIX #9107",
                        "updated": "2026-11-23T03:50:00Z",
                    }
                ],
            }
        }
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    monkeypatch.setenv("BOB_OPENCODE_SEATS_FIXTURE", str(path))
    monkeypatch.setenv("BOB_OPENCODE_MONITOR_MACHINES", "redqueen")
    monkeypatch.setenv("BOB_OPENCODE_EXPECT_SEATS", "2")
    payload, code = mod.check(None)
    assert code != 0
    assert payload.get("expect_seats") == 2
    assert any("under-count" in f for f in payload.get("findings") or [])
    assert payload.get("under_count")