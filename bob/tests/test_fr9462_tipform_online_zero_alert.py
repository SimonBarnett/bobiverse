"""FR #9462: TipForm durable online_zero_workers alert helpers."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

START = ROOT / "third_party" / "bob-tray" / "tools" / "BobTrayStartWorker.ps1"
HOVER = ROOT / "third_party" / "bob-tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
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


def test_fr9462_source_pins_helpers_and_watch():
    start = START.read_text(encoding="utf-8")
    hover = HOVER.read_text(encoding="utf-8")
    watch = WATCH.read_text(encoding="utf-8")
    assert "function Get-BobTrayOnlineZeroWorkerAlerts" in start
    assert "function Format-BobTrayOnlineZeroCaption" in start
    assert "online_zero_workers" in start
    assert "FR #9462" in start
    assert "FR #3180" in start
    assert "online_zero_workers" in hover
    assert "Get-BobTrayOnlineZeroWorkerAlerts" in hover
    assert "online_zero_caption" in hover
    assert "Get-BobTrayOnlineZeroWorkerAlerts" in watch
    assert "FR #9462" in watch


@WIN
def test_fr9462_alerts_when_online_empty_and_offerable(tmp_path: Path):
    out = _ps(
        tmp_path,
        r"""
. "%s"
$machines = [pscustomobject]@{
  marchhare = [pscustomobject]@{ online = $true; workers = @{} }
  flamingo  = [pscustomobject]@{ online = $true; workers = @(@{ nick = 'flamingo-1' }) }
}
$a = @(Get-BobTrayOnlineZeroWorkerAlerts -Machines $machines -OfferableCount 17)
$c = Format-BobTrayOnlineZeroCaption -Machines $machines -OfferableCount 17
Write-Output ("count={0}" -f $a.Count)
Write-Output ("caption={0}" -f $c)
Write-Output ("alert0={0}" -f $a[0])
"""
        % START.as_posix(),
    )
    text = out.replace("\r", "")
    assert "count=1" in text
    assert "marchhare" in text
    assert "TipForm Agents" in text
    assert "offerable=17" in text


@WIN
def test_fr9462_silent_when_offerable_zero(tmp_path: Path):
    out = _ps(
        tmp_path,
        r"""
. "%s"
$machines = [pscustomobject]@{
  marchhare = [pscustomobject]@{ online = $true; workers = @{} }
}
$a = @(Get-BobTrayOnlineZeroWorkerAlerts -Machines $machines -OfferableCount 0)
Write-Output ("count={0}" -f $a.Count)
"""
        % START.as_posix(),
    )
    assert "count=0" in out.replace("\r", "")
