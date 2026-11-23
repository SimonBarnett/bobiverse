"""FR #9142: empty-online.disabled + no auto->grok when fuel gate fails.

Ops on redqueen: file run/startworker/empty-online.disabled to stop TipForm
empty-online fill without seat_target=0. When grok remaining is known 0 and
opencode free is not viable, skip fill (log empty-online skip: no-fuel) instead
of kind=auto resolving to Grok zombies. Related #9000 / #9023.
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


def test_fr9142_source_pins_disabled_and_skip():
    start = START.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    assert "function Test-BobTrayEmptyOnlineDisabled" in start
    assert "empty-online.disabled" in start
    assert "FR #9142" in start
    assert "skip" in start
    assert "no-fuel" in start
    assert "Test-BobTrayEmptyOnlineDisabled" in watch
    assert "empty-online skip:" in watch
    assert "FR #9142" in watch
    # Disabled returns fill count 0 without seats-off.
    assert "-Disabled" in start or "Disabled" in start


@WIN
def test_fr9142_disabled_file_zeros_fill_count(tmp_path: Path):
    sw = tmp_path / "run" / "startworker"
    sw.mkdir(parents=True)
    (sw / "empty-online.disabled").write_text("operator\n", encoding="utf-8")
    out = _ps(
        tmp_path,
        r"""
. "%s"
$d = Test-BobTrayEmptyOnlineDisabled -Root "%s"
$n = Get-BobTrayEmptyOnlineFillCount -LiveAgents 0 -PendingReqs 0 -SeatsOff $false -Cooldown $false -Cap 2 -Disabled $d
Write-Output ("{0}|{1}" -f $d, $n)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    assert "True|0" in out.replace("\r", "")


@WIN
def test_fr9142_absent_disabled_allows_fill(tmp_path: Path):
    (tmp_path / "run" / "startworker").mkdir(parents=True)
    out = _ps(
        tmp_path,
        r"""
. "%s"
$d = Test-BobTrayEmptyOnlineDisabled -Root "%s"
$n = Get-BobTrayEmptyOnlineFillCount -LiveAgents 0 -PendingReqs 0 -SeatsOff $false -Cooldown $false -Cap 2 -Disabled $d
Write-Output ("{0}|{1}" -f $d, $n)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    assert "False|2" in out.replace("\r", "")


@WIN
def test_fr9142_grok_zero_free_zero_skips_not_auto(tmp_path: Path):
    out = _ps(
        tmp_path,
        r"""
. "%s"
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 0 -Root "%s"
$skip = if ($c.skip) { '1' } else { '0' }
$agent = if ($c.agent) { $c.agent } else { 'auto' }
Write-Output ("{0}|{1}|{2}" -f $skip, $agent, $c.reason)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    line = out.replace("\r", "").strip().splitlines()[-1]
    assert line.startswith("1|auto|") or line.startswith("1|")
    assert "no-fuel" in line
    assert "opencode|" not in line


@WIN
def test_fr9142_grok_zero_free_ok_still_pins_opencode(tmp_path: Path):
    # Stub Resolve so pin path works without full tray fuel helpers.
    out = _ps(
        tmp_path,
        r"""
. "%s"
function Resolve-BobTrayOpencodeSlotModel { param($Root,$Slot) return 'free-leaf' }
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 40 -Root "%s"
$skip = if ($c.skip) { '1' } else { '0' }
Write-Output ("{0}|{1}|{2}" -f $skip, $c.agent, $c.slot)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    assert "0|opencode|free" in out.replace("\r", "")


@WIN
def test_fr9142_no_leaf_skips_when_grok_zero(tmp_path: Path):
    out = _ps(
        tmp_path,
        r"""
. "%s"
function Resolve-BobTrayOpencodeSlotModel { param($Root,$Slot) return '' }
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 40 -Root "%s"
$skip = if ($c.skip) { '1' } else { '0' }
Write-Output ("{0}|{1}" -f $skip, $c.reason)
"""
        % (START.as_posix(), tmp_path.as_posix()),
    )
    assert "1|no-fuel" in out.replace("\r", "")
