"""FR #9240: empty-online.disabled blocks every auto seat-start path.

Regression of #9195 / #9142: fill helpers returned 0, but startworker queue
(auto-start) and recycle restore still launched seats. Standing rule: seats
start only from TipForm clicks (and explicit !startworker); auto fill /
restart / resume / recycle restore must refuse when the kill switch is present
and log + dedupe-intake the attempt.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

TRAY_TOOLS = ROOT / "third_party" / "bob-tray" / "tools"
START = TRAY_TOOLS / "BobTrayStartWorker.ps1"
WATCH = TRAY_TOOLS / "Watch-BobTray.ps1"
POST = ROOT / "common" / "docs" / "post-install.md"
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


def test_fr9240_source_pins_auto_gate_and_intake():
    start = START.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    assert "function Test-BobTraySeatStartTriggerIsAuto" in start
    assert "function Test-BobTrayEmptyOnlineBlocksAutoStart" in start
    assert "function Write-BobTrayUnrequestedSeatStartIntake" in start
    assert "empty-online-disabled" in start
    assert "FR #9240" in start
    assert "FR #9240" in watch
    # Central refuse in Start-BobTrayWorkerExe for auto triggers.
    assert "Test-BobTrayEmptyOnlineBlocksAutoStart" in watch
    assert "restore-after-recycle" in start
    assert "auto-start" in start
    # Manual TipForm triggers stay allowlisted.
    assert "workers-opencode" in start or "menu" in start
    # Explicit !startworker keeps a non-auto trigger name.
    assert "startworker" in start
    assert "empty-online.disabled" in post
    assert "FR #9240" in post or "9240" in post


@WIN
def test_fr9240_auto_triggers_blocked_when_disabled(tmp_path: Path):
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    out = _ps(
        tmp_path,
        r"""
. "%s"
$root = "%s"
$a = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'auto-start'
$b = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'restore-after-recycle'
$c = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'menu'
$d = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'workers-opencode'
$e = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'startworker'
$f = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'jeeves-menu'
Write-Output ("{0}|{1}|{2}|{3}|{4}|{5}" -f $a,$b,$c,$d,$e,$f)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    # auto + recycle blocked; menu / workers / startworker / jeeves allowed
    assert "True|True|False|False|False|False" in out.replace("\r", "")


@WIN
def test_fr9240_absent_disabled_allows_auto(tmp_path: Path):
    (tmp_path / "run" / "startworker").mkdir(parents=True)
    out = _ps(
        tmp_path,
        r"""
. "%s"
$a = Test-BobTrayEmptyOnlineBlocksAutoStart -Root "%s" -Trigger 'auto-start'
$b = Test-BobTrayEmptyOnlineBlocksAutoStart -Root "%s" -Trigger 'restore-after-recycle'
Write-Output ("{0}|{1}" -f $a,$b)
"""
        % (START.as_posix(), tmp_path.as_posix(), tmp_path.as_posix()),
    )
    assert "False|False" in out.replace("\r", "")


@WIN
def test_fr9240_queue_refuses_kind_auto_when_disabled(tmp_path: Path):
    """startworker queue must not Launch kind=auto while empty-online.disabled exists."""
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    # Far-future unix so ConvertTo-BobTrayStartWorkerExpires is not 'expired'.
    now = 2000000000
    req = (
        '{"id":"empty-%d-0","mode":"agent","by":"tray","kind":"auto",'
        '"ts":%d,"expires":%d}'
    ) % (now, now, now + 3600)
    (sw / ("req-empty-%d-0.json" % now)).write_text(req, encoding="ascii")
    launched = tmp_path / "launched.txt"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$script:RepoRoot = "%s"
$launchLog = "%s"
function Test-BobTraySeatsOff { return $false }
function Get-BobTrayWorkerCapRefusal { param($Mode) return '' }
$tick = [datetime]::SpecifyKind(([datetime]'2033-05-18T03:33:20Z'), 'Utc')
$results = @(Invoke-BobTrayStartWorkerQueue -Dir "%s" `
  -Launch { param($mode,$agent,$model,$trigger) Add-Content -LiteralPath $launchLog -Value ("LAUNCH|{0}|{1}" -f $mode,$trigger); return 4242 } `
  -Log { param($m) } `
  -Now $tick `
  -Root "%s")
$r = @($results | Where-Object { $_.PSObject.Properties.Name -contains 'reason' }) | Select-Object -First 1
if (-not $r) { Write-Output 'RESULT|none'; Write-Output 'NO_LAUNCH'; return }
$ok = if ($r.ok) { '1' } else { '0' }
Write-Output ("RESULT|{0}|{1}|{2}" -f $ok, $r.reason, $r.pid)
if (Test-Path -LiteralPath $launchLog) { Get-Content -LiteralPath $launchLog } else { Write-Output 'NO_LAUNCH' }
"""
        % (
            START.as_posix(),
            tmp_path.as_posix(),
            launched.as_posix(),
            sw.as_posix(),
            tmp_path.as_posix(),
        ),
    )
    text = out.replace("\r", "")
    assert "RESULT|0|empty-online-disabled|0" in text, text
    assert "LAUNCH|" not in text


@WIN
def test_fr9240_queue_allows_explicit_startworker_when_disabled(tmp_path: Path):
    """Explicit !startworker (no kind=auto) still launches under the kill switch."""
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    now = 2000000100
    req = (
        '{"id":"ear-%d","mode":"agent","by":"ear","ts":%d,"expires":%d}'
    ) % (now, now, now + 3600)
    (sw / ("req-ear-%d.json" % now)).write_text(req, encoding="ascii")
    launched = tmp_path / "launched.txt"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$script:RepoRoot = "%s"
$launchLog = "%s"
function Test-BobTraySeatsOff { return $false }
function Get-BobTrayWorkerCapRefusal { param($Mode) return '' }
$tick = [datetime]::SpecifyKind(([datetime]'2033-05-18T03:35:00Z'), 'Utc')
$results = @(Invoke-BobTrayStartWorkerQueue -Dir "%s" `
  -Launch { param($mode,$agent,$model,$trigger) Add-Content -LiteralPath $launchLog -Value ("LAUNCH|{0}|{1}" -f $mode,$trigger); return 5150 } `
  -Log { param($m) } `
  -Now $tick `
  -Root "%s")
$r = @($results | Where-Object { $_.PSObject.Properties.Name -contains 'reason' }) | Select-Object -First 1
if (-not $r) { Write-Output 'RESULT|none'; Write-Output 'NO_LAUNCH'; return }
$ok = if ($r.ok) { '1' } else { '0' }
Write-Output ("RESULT|{0}|{1}|{2}" -f $ok, $r.reason, $r.pid)
if (Test-Path -LiteralPath $launchLog) { Get-Content -LiteralPath $launchLog } else { Write-Output 'NO_LAUNCH' }
"""
        % (
            START.as_posix(),
            tmp_path.as_posix(),
            launched.as_posix(),
            sw.as_posix(),
            tmp_path.as_posix(),
        ),
    )
    text = out.replace("\r", "")
    assert "RESULT|1|" in text or "LAUNCH|agent|startworker" in text, text
    assert "LAUNCH|agent|startworker" in text, text
    assert "empty-online-disabled" not in text.split("RESULT|")[-1].splitlines()[0]


@WIN
def test_fr9240_intake_dedup_stamp(tmp_path: Path):
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    out = _ps(
        tmp_path,
        r"""
. "%s"
$root = "%s"
# Dry: helper must write dedup stamp without throwing when Report script is absent.
$r1 = Write-BobTrayUnrequestedSeatStartIntake -Root $root -Trigger 'auto-start' -Site 'test'
$r2 = Write-BobTrayUnrequestedSeatStartIntake -Root $root -Trigger 'auto-start' -Site 'test'
Write-Output ("{0}|{1}" -f $r1,$r2)
$stamp = Join-Path (Join-Path $root 'run\startworker') 'unrequested-start.intake'
Write-Output ("STAMP|{0}" -f (Test-Path -LiteralPath $stamp))
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    text = out.replace("\r", "")
    # first filed (or attempted), second skipped as dedup
    assert "True|False" in text or "1|0" in text, text
    assert "STAMP|True" in text
