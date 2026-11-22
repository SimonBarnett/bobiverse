"""FR #9000: empty-online fill prefers opencode free when grok remaining is 0."""
from __future__ import annotations

import subprocess
import sys
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


def test_source_pins_empty_online_choice():
    start = (TRAY_TOOLS / "BobTrayStartWorker.ps1").read_text(encoding="utf-8")
    assert "function Get-BobTrayEmptyOnlineFillAgentChoice" in start
    assert "FR #9000" in start
    watch = (TRAY_TOOLS / "Watch-BobTray.ps1").read_text(encoding="utf-8")
    assert "Get-BobTrayEmptyOnlineFillAgentChoice" in watch
    assert "empty-online fill reqs={0} agent={1} slot={2}" in watch


@WIN
def test_grok_zero_pins_opencode_free(tmp_path: Path):
    helper = TRAY_TOOLS / "BobTrayStartWorker.ps1"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 40 -Root "%s"
Write-Output ("{0}|{1}" -f $c.agent, $c.slot)
"""
        % (helper.as_posix(), tmp_path.as_posix()),
    )
    assert "opencode|free" in out.replace("\r", "")


@WIN
def test_grok_nonzero_stays_auto(tmp_path: Path):
    helper = TRAY_TOOLS / "BobTrayStartWorker.ps1"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 12 -OpencodeFreeRemaining 40 -Root "%s"
Write-Output ("{0}|{1}" -f $(if ($c.agent) { $c.agent } else { 'auto' }), $(if ($c.slot) { $c.slot } else { '-' }))
"""
        % (helper.as_posix(), tmp_path.as_posix()),
    )
    assert "auto|-" in out.replace("\r", "")


@WIN
def test_grok_unknown_stays_auto(tmp_path: Path):
    helper = TRAY_TOOLS / "BobTrayStartWorker.ps1"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining $null -OpencodeFreeRemaining 40 -Root "%s"
Write-Output ("{0}|{1}" -f $(if ($c.agent) { $c.agent } else { 'auto' }), $(if ($c.slot) { $c.slot } else { '-' }))
"""
        % (helper.as_posix(), tmp_path.as_posix()),
    )
    assert "auto|-" in out.replace("\r", "")


@WIN
def test_free_known_zero_stays_auto(tmp_path: Path):
    helper = TRAY_TOOLS / "BobTrayStartWorker.ps1"
    out = _ps(
        tmp_path,
        r"""
. "%s"
$c = Get-BobTrayEmptyOnlineFillAgentChoice -GrokRemaining 0 -OpencodeFreeRemaining 0 -Root "%s"
Write-Output ("{0}|{1}" -f $(if ($c.agent) { $c.agent } else { 'auto' }), $(if ($c.slot) { $c.slot } else { '-' }))
"""
        % (helper.as_posix(), tmp_path.as_posix()),
    )
    assert "auto|-" in out.replace("\r", "")
