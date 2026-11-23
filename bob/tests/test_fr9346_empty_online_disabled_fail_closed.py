"""FR #9346: empty-online.disabled fail-closed shared guard (regression of #9240).

Tray a4811d0b auto-started Grok seats on redqueen with the kill switch present.
#9240 allowlisted auto triggers and left unknown/default Trigger='other' fail-open.
Standing rule: every automatic seat-start path refuses while empty-online.disabled
exists, through one shared guard; TipForm clicks and explicit !startworker stay allowed.
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
RECYCLE = TRAY_TOOLS / "BobTrayRecycleSeat.ps1"
CLICKED = TRAY_TOOLS / "BobTrayClickedSeats.ps1"
CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
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


def test_fr9346_source_pins_fail_closed_shared_guard():
    start = START.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    recycle = RECYCLE.read_text(encoding="utf-8")
    cs = CS.read_text(encoding="utf-8-sig")
    post = POST.read_text(encoding="utf-8")
    assert "function Test-BobTraySeatStartTriggerIsManual" in start
    assert "FR #9346" in start
    assert "fail-closed" in start.lower() or "fail closed" in start.lower() or "not manual" in start.lower()
    # Start-BobTrayWorkerExe still central-refuses via the shared gate.
    assert "Test-BobTrayEmptyOnlineBlocksAutoStart" in watch
    # Recycle refusal mirrors the shared gate (not only Start-BobTrayWorkerExe).
    assert "Test-BobTrayEmptyOnlineBlocksAutoStart" in recycle or "EmptyOnline" in recycle
    # TipForm C# shares the same contract (manual TipForm triggers stay allowed).
    assert "EmptyOnlineDisabled" in cs or "empty-online.disabled" in cs
    assert "EmptyOnlineBlocksAutoStart" in cs or "SeatStartTriggerIsManual" in cs
    assert "FR #9346" in post or "9346" in post


@WIN
def test_fr9346_unknown_and_default_triggers_blocked_when_disabled(tmp_path: Path):
    """Fail-closed: other / empty / unknown are auto while the kill switch is present."""
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    out = _ps(
        tmp_path,
        r"""
. "%s"
$root = "%s"
$a = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'other'
$b = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger ''
$c = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'restore-last-good'
$d = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'engine-restart'
$e = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'menu'
$f = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'workers-grok'
$g = Test-BobTrayEmptyOnlineBlocksAutoStart -Root $root -Trigger 'startworker'
Write-Output ("{0}|{1}|{2}|{3}|{4}|{5}|{6}" -f $a,$b,$c,$d,$e,$f,$g)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    # unknown/default blocked; TipForm + !startworker allowed
    assert "True|True|True|True|False|False|False" in out.replace("\r", ""), out


@WIN
def test_fr9346_cold_start_recorded_seats_zero_launches(tmp_path: Path):
    """Cold start with flag + clicked-seats (Grok + OpenCode): auto queue + recycle restore launch 0."""
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    # Previously recorded seats (identity only) must not cause a start.
    clicked = tmp_path / "run" / "clicked-seats.txt"
    clicked.write_text(
        "redqueen-111\tgrok\tredqueen\tEXAMPLE_GROK\n"
        "redqueen-222\topencode\tredqueen\texample/opencode-free\n",
        encoding="ascii",
    )
    rs = tmp_path / "run" / "recycleseat"
    rs.mkdir(parents=True)
    now = 2000000200
    # Pending auto fill + a recycle restore for a recorded nick.
    (sw / ("req-empty-%d-0.json" % now)).write_text(
        '{"id":"empty-%d-0","mode":"agent","by":"tray","kind":"auto","agent":"grok",'
        '"ts":%d,"expires":%d}' % (now, now, now + 3600),
        encoding="ascii",
    )
    (rs / ("req-recycle-%d.json" % now)).write_text(
        '{"id":"recycle-%d","nick":"redqueen-111","by":"test","ts":%d,"expires":%d}'
        % (now, now, now + 3600),
        encoding="ascii",
    )
    launched = tmp_path / "launched.txt"
    out = _ps(
        tmp_path,
        r"""
. "%s"
. "%s"
. "%s"
$script:RepoRoot = "%s"
$launchLog = "%s"
function Test-BobTraySeatsOff { return $false }
function Get-BobTrayWorkerCapRefusal { param($Mode) return '' }
function Resolve-BobTrayRecyclePid { param($MarkerPid, $Nick) return 0 }
function Get-BobTraySeatMarkerPid { param($Nick) return 0 }
$tick = [datetime]::SpecifyKind(([datetime]'2033-05-18T03:36:40Z'), 'Utc')
$q = @(Invoke-BobTrayStartWorkerQueue -Dir "%s" `
  -Launch { param($mode,$agent,$model,$trigger) Add-Content -LiteralPath $launchLog -Value ("Q|{0}|{1}" -f $mode,$trigger); return 9001 } `
  -Log { param($m) } `
  -Now $tick `
  -Root "%s")
$r = @(Invoke-BobTrayRecycleSeatQueue -Root "%s" -Dir "%s" `
  -Launch { param($seatNick,$kind,$model) Add-Content -LiteralPath $launchLog -Value ("R|{0}|{1}" -f $seatNick,$kind); return 9002 } `
  -Log { param($m) } `
  -Now $tick)
$qr = @($q | Where-Object { $_.PSObject.Properties.Name -contains 'reason' }) | Select-Object -First 1
if ($qr) { Write-Output ("QRESULT|{0}|{1}" -f $(if ($qr.ok) {'1'} else {'0'}), $qr.reason) } else { Write-Output 'QRESULT|none' }
if (Test-Path -LiteralPath $launchLog) { Get-Content -LiteralPath $launchLog } else { Write-Output 'NO_LAUNCH' }
# Shared guard must block default/other even at Start-BobTrayWorkerExe.
$blockOther = Test-BobTrayEmptyOnlineBlocksAutoStart -Root "%s" -Trigger 'other'
$blockAuto = Test-BobTrayEmptyOnlineBlocksAutoStart -Root "%s" -Trigger 'auto-start'
$blockRestore = Test-BobTrayEmptyOnlineBlocksAutoStart -Root "%s" -Trigger 'restore-after-recycle'
Write-Output ("GATE|{0}|{1}|{2}" -f $blockOther,$blockAuto,$blockRestore)
Write-Output ("CLICKED|{0}" -f (Test-Path -LiteralPath "%s"))
"""
        % (
            START.as_posix(),
            CLICKED.as_posix(),
            RECYCLE.as_posix(),
            tmp_path.as_posix(),
            launched.as_posix(),
            sw.as_posix(),
            tmp_path.as_posix(),
            tmp_path.as_posix(),
            rs.as_posix(),
            tmp_path.as_posix(),
            tmp_path.as_posix(),
            tmp_path.as_posix(),
            clicked.as_posix(),
        ),
    )
    text = out.replace("\r", "")
    assert "QRESULT|0|empty-online-disabled" in text, text
    assert "Q|" not in text, text
    assert "R|" not in text, text
    assert "GATE|True|True|True" in text, text
    assert "CLICKED|True" in text, text


@WIN
def test_fr9346_manual_triggers_still_allowed(tmp_path: Path):
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    out = _ps(
        tmp_path,
        r"""
. "%s"
$root = "%s"
$m = Test-BobTraySeatStartTriggerIsManual -Trigger 'menu'
$w = Test-BobTraySeatStartTriggerIsManual -Trigger 'workers-opencode'
$j = Test-BobTraySeatStartTriggerIsManual -Trigger 'jeeves-menu'
$s = Test-BobTraySeatStartTriggerIsManual -Trigger 'startworker'
$o = Test-BobTraySeatStartTriggerIsManual -Trigger 'other'
$a = Test-BobTraySeatStartTriggerIsManual -Trigger 'auto-start'
Write-Output ("{0}|{1}|{2}|{3}|{4}|{5}" -f $m,$w,$j,$s,$o,$a)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    assert "True|True|True|True|False|False" in out.replace("\r", ""), out


def test_fr9346_healengine_never_launches_seats_source():
    """#9280 engine restart path must never call WorkerLauncher.Launch (flag or not)."""
    t = CS.read_text(encoding="utf-8-sig")
    i = t.find("void HealEngine()")
    assert i >= 0
    rest = t[i:]
    nxt = rest.find("\n        void ", 1)
    body = rest if nxt < 0 else rest[:nxt]
    assert "WorkerLauncher.Launch" not in body
    assert "StartWorker(" not in body
    assert "status-writer" in body.lower() or "Never starts" in body or "never starts" in body.lower()
