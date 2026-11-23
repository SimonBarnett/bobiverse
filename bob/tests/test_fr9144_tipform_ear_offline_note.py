# -*- coding: utf-8 -*-
"""FR #9144: TipForm distinguishes ear-offline from digest unreachable."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOVER = ROOT / "tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
PS = os.environ.get("BOB_TEST_POWERSHELL") or shutil.which("powershell") or shutil.which("pwsh")
needs_ps = pytest.mark.skipif(not PS or os.name != "nt", reason="needs Windows PowerShell")


def test_fr9144_source_pins_ear_offline_helpers():
    text = HOVER.read_text(encoding="utf-8-sig")
    assert "function Test-BobTrayDigestEarOffline" in text
    assert "function Resolve-BobTrayDigestFailNote" in text
    assert "function Get-BobTrayIrcBobServiceStatus" in text
    assert "digest ear-offline:" in text
    assert "FR #9144" in text


@needs_ps
def test_fr9144_resolve_prefers_ear_offline_when_online_false():
    script = r"""
. '%s'
$doc = [pscustomobject]@{
  machines = [pscustomobject]@{
    redqueen = [pscustomobject]@{ online = $false; status = 'I am offline' }
  }
}
$n = Resolve-BobTrayDigestFailNote -DigestErr 'Exception calling GetResponse' -Doc $doc -LocalMachineId 'redqueen' -IrcBobStatus 'Running'
if ($n -notmatch 'ear-offline') { 'FAIL:' + $n; exit 1 }
if ($n -match '^digest unreachable:') { 'FAIL-unreachable:' + $n; exit 1 }
'OK:' + $n
""" % str(HOVER).replace("'", "''")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK:" in r.stdout
    assert "ear-offline" in r.stdout


@needs_ps
def test_fr9144_resolve_unreachable_when_online():
    script = r"""
. '%s'
$doc = [pscustomobject]@{
  machines = [pscustomobject]@{
    flamingo = [pscustomobject]@{ online = $true; status = 'I am online' }
  }
}
$n = Resolve-BobTrayDigestFailNote -DigestErr 'Exception calling GetResponse' -Doc $doc -LocalMachineId 'flamingo' -IrcBobStatus 'Running'
if ($n -notmatch '^digest unreachable:') { 'FAIL:' + $n; exit 1 }
'OK:' + $n
""" % str(HOVER).replace("'", "''")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK:" in r.stdout


@needs_ps
def test_fr9144_resolve_ear_offline_when_ircbob_stopped():
    script = r"""
. '%s'
$n = Resolve-BobTrayDigestFailNote -DigestErr 'GetResponse timeout' -Doc $null -LocalMachineId '' -IrcBobStatus 'Stopped'
if ($n -notmatch 'ear-offline') { 'FAIL:' + $n; exit 1 }
'OK:' + $n
""" % str(HOVER).replace("'", "''")
    r = subprocess.run(
        [PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ircBob Status=Stopped" in r.stdout
