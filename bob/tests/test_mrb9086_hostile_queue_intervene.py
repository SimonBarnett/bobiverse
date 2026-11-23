"""MRB #9086 hostile: Invoke-BobQueueIntervene writes nudge and reports action."""
from __future__ import annotations

import subprocess
from pathlib import Path

from repo_layout import ROOT

SRC = ROOT / "bob" / "tray" / "src" / "Private" / "Get-BobStallAlerts.ps1"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_mrb9086_intervene_empty_alerts_no_nudge(tmp_path: Path):
    script = tmp_path / "run.ps1"
    nudge_dir = tmp_path / "sw"
    nudge_dir.mkdir()
    script.write_text(
        r"""
$ErrorActionPreference = 'Stop'
. '%s'
$r = Invoke-BobQueueIntervene -Alerts @() -StartWorkerDir '%s'
if ($r.Intervened) { throw 'empty alerts must not intervene' }
if ($r.Action -ne 'none') { throw ('bad action ' + $r.Action) }
if (Test-Path -LiteralPath (Join-Path '%s' 'queue-intervene.nudge')) { throw 'nudge must not exist' }
Write-Output 'ok'
"""
        % (
            str(SRC).replace("'", "''"),
            str(nudge_dir).replace("'", "''"),
            str(nudge_dir).replace("'", "''"),
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_mrb9086_intervene_writes_nudge_and_logline(tmp_path: Path):
    script = tmp_path / "run.ps1"
    nudge_dir = tmp_path / "sw"
    nudge_dir.mkdir()
    script.write_text(
        r"""
$ErrorActionPreference = 'Stop'
. '%s'
$r = Invoke-BobQueueIntervene -Alerts @('seat hung') -StartWorkerDir '%s'
if (-not $r.Intervened) { throw 'expected Intervened' }
if ($r.Action -ne 'nudge-under-cap-fill') { throw ('bad action ' + $r.Action) }
if ($r.LogLine -notmatch 'queue-intervene action=nudge-under-cap-fill') { throw ('bad log ' + $r.LogLine) }
$nudge = Join-Path '%s' 'queue-intervene.nudge'
if (-not (Test-Path -LiteralPath $nudge)) { throw 'missing nudge file' }
Write-Output 'ok'
"""
        % (
            str(SRC).replace("'", "''"),
            str(nudge_dir).replace("'", "''"),
            str(nudge_dir).replace("'", "''"),
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "ok" in proc.stdout


def test_mrb9086_watch_wires_intervene_after_stall_fr():
    text = WATCH.read_text(encoding="utf-8")
    stall = text.find("Get-BobStallFrIntake")
    intervene = text.find("Invoke-BobQueueIntervene")
    assert stall >= 0 and intervene > stall
    assert "queue-intervene.nudge" in text
    assert "$cool = $false" in text or "$cool = $false" in text.replace(" ", "")
    # Fresh nudge clears under-cap / empty-fill cooldown.
    assert "nage -lt 120" in text or "$nage -lt 120" in text
