"""FR #5688: digest running/jobs/repo count only fleet-backed grok, not PriorityAgent sessions."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

HOVER = ROOT / "third_party" / "bob-tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "third_party" / "bob-tray" / "src" / "Private" / "Get-BobIrc.ps1"
PSM1 = ROOT / "third_party" / "bob-tray" / "src" / "BobBridge.psm1"
PSD1 = ROOT / "third_party" / "bob-tray" / "src" / "BobBridge.psd1"

PS = shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr5688_source_pins_fleet_seat_helper_and_digest_filter():
    hover = _txt(HOVER)
    assert "function Test-BobLiveGrokIsFleetSeat" in hover
    assert "FR #5688" in hover
    assert "fleetSeat" in hover
    irc = _txt(IRC)
    write = irc[irc.index("function Write-BobIrcStatus") :]
    # Digest must skip non-fleet live grok (PriorityAgent / user-hosted).
    assert "fleetSeat" in write
    assert "FR #5688" in write
    psm = _txt(PSM1)
    assert "Test-BobLiveGrokIsFleetSeat" in psm
    psd = _txt(PSD1)
    assert "Test-BobLiveGrokIsFleetSeat" in psd


@needs_ps
def test_fr5688_fleet_seat_classifier_priority_agent_false_bob_worker_true():
    script = r"""
$ErrorActionPreference = 'Stop'
. '{hover}'
if (-not (Get-Command Test-BobLiveGrokIsFleetSeat -ErrorAction SilentlyContinue)) {{
  throw 'Test-BobLiveGrokIsFleetSeat missing'
}}
$pa = Test-BobLiveGrokIsFleetSeat -ParentName 'PriorityAgent.exe' -AncestorNames @('PriorityAgent.exe','explorer.exe')
if ($pa) {{ throw 'PriorityAgent parent must not be fleet seat' }}
$bw = Test-BobLiveGrokIsFleetSeat -ParentName 'agent.exe' -AncestorNames @('agent.exe','bob-worker.exe')
if (-not $bw) {{ throw 'bob-worker ancestor must be fleet seat' }}
$bw2 = Test-BobLiveGrokIsFleetSeat -ParentName 'bob-worker-aaa.exe' -ParentPath 'C:\ai\bob\worker\bob-worker-aaa.exe'
if (-not $bw2) {{ throw 'bob-worker-*.exe parent must be fleet seat' }}
Write-Output 'CLASSIFY_OK'
""".format(
        hover=str(HOVER).replace("'", "''")
    )
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        timeout=60,
    )
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err or out
    assert "CLASSIFY_OK" in out


@needs_ps
def test_fr5688_write_status_ignores_non_fleet_live_grok(tmp_path: Path):
    """Empty lanes + PriorityAgent-backed live grok => running=0, jobs=[], repo unset."""
    tray = ROOT / "third_party" / "bob-tray"
    body = f"""
$ErrorActionPreference = 'Stop'
Import-Module '{tray / "src" / "BobBridge.psd1"}' -Force -DisableNameChecking
& (Get-Module BobBridge) {{
  # Empty fleet lanes.
  function script:Get-BobPeerLaneJobs {{ param($BridgeRoot,$MachineId,$Lane,[switch]$StampRepo) @() }}
  function script:Filter-BobFleetLaneJobsLive {{ param($Jobs) @() }}
  # One user-hosted grok (PriorityAgent) that must NOT count as digest running.
  function script:Get-BobLiveGrokAgents {{
    ,[pscustomobject]@{{
      id = 'grok-21880'
      sessionId = 'grok-21880'
      pid = 21880
      cwd = 'D:\\ai\\hrsmith\\120.1'
      claimedAt = '2026-10-29T20:06:01.2422981Z'
      machine = $null
      state = 'running'
      source = 'live-grok'
      parentName = 'PriorityAgent.exe'
      fleetSeat = $false
    }}
  }}
  function script:Get-GitHubSlugFromCwd {{ param($Path) 'SimonBarnett/hrsmith' }}
  $doc = Write-BobIrcStatus -PassThru -SkipDigestWebhook
  if (-not $doc) {{ throw 'Write-BobIrcStatus returned nothing' }}
  if ([int]$doc.running -ne 0) {{ throw ("running={{0}} want 0" -f $doc.running) }}
  if (@($doc.jobs).Count -ne 0) {{ throw ("jobs count={{0}}" -f @($doc.jobs).Count) }}
  if ($doc.repo) {{ throw ("repo={{0}} want unset" -f $doc.repo) }}
  Write-Output 'DIGEST_OK'
}}
"""
    script = tmp_path / "t.ps1"
    script.write_bytes(("\ufeff" + body).encode("utf-8"))
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        capture_output=True,
        timeout=180,
    )
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    assert r.returncode == 0, err or out
    assert "DIGEST_OK" in out
