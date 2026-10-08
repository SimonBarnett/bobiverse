"""FR #3513 helpers + FR #3512 flat nicks; FR #3639 fleet Resolve returns empty (irc_ops)."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UPDATE = ROOT / "common/scripts/Update-BobiverseService.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
ROSTER = ROOT / "airc/config/fleet-operators.txt"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_fr3513_roster_file_ships_cross_machine_ear():
    assert ROSTER.is_file()
    body = ROSTER.read_text(encoding="utf-8")
    assert "bob-win-mpre8vi4u6u" in body
    assert "FR #3513" in body or "3513" in body


def test_fr3513_common_helpers_and_install_update_wire():
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "function Get-BobiverseAircFleetOperatorRoster" in common
    assert "FR #3513" in common
    assert "Write-Output -NoEnumerate" in common  # FR #3512 flat return
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "InstallRoot" in inst and "Resolve-BobiverseAircOperatorNicks" in inst
    assert "FR #3513" in inst or "fleet-operators" in inst or "FR #3639" in inst
    upd = UPDATE.read_text(encoding="utf-8-sig")
    assert "Get-AircSelfUpdateOperatorsProperty" in upd
    assert "AIRC_OPERATORS=" in upd
    assert "FR #3513" in upd
    pack = PACK.read_text(encoding="utf-8-sig")
    assert "fleet-operators.txt" in pack


def test_fr3513_docs_skill_call_out_self_update_break():
    blob = POST.read_text(encoding="utf-8") + "\n" + SKILL.read_text(encoding="utf-8")
    assert "3513" in blob or "3639" in blob
    assert "fleet-operators" in blob.lower() or "AIRC_OPERATORS" in blob or "irc_ops" in blob


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3513_resolve_unions_roster_and_stays_flat(tmp_path: Path):
    """FR #3639: fleet Resolve returns empty; workstation stays flat (#3512)."""
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "fleet-operators.txt").write_text(
        "# comment\nbob-win-mpre8vi4u6u\n", encoding="utf-8"
    )
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $ops = Resolve-BobiverseAircOperatorNicks -Profile 'fleet' `
            -Operators @('Simon') -OperatorsExtra '' -InstallRoot '{root}'
        $join = (@($ops) -join ',')
        if ($join) {{ throw "FR #3639 fleet must be empty: $join" }}
        $ws = Resolve-BobiverseAircOperatorNicks -Profile 'workstation' `
            -Operators @('Simon') -OperatorsExtra 'bob-evil' -InstallRoot '{root}'
        if ($ws.Count -eq 1 -and $ws[0] -is [Array]) {{
            throw "nested array (FR #3512): $($ws[0] -join ' ')"
        }}
        $wsj = (@($ws) -join ',')
        if ($wsj -notmatch '(?i)^Simon$') {{ throw "workstation ops unexpected: $wsj" }}
        Write-Output ('ok:' + $wsj)
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "ok:" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3513_merge_after_resolve_authorises_cross_machine(tmp_path: Path):
    """FR #3639: fleet Resolve empty; Merge still writes flat nicks (workstation path)."""
    home = tmp_path / ".airc"
    home.mkdir()
    ops = home / "operators.txt"
    ops.write_text("Simon\nbob-marchhare\n", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $ops = Resolve-BobiverseAircOperatorNicks -Profile 'fleet' `
            -Operators @('Simon') -OperatorsExtra 'bob-win-mpre8vi4u6u' -InstallRoot '{tmp_path}'
        if ((@($ops) -join ',')) {{ throw "fleet resolve must be empty: $(@($ops) -join ',')" }}
        Merge-BobiverseAircOperatorsFile -Path '{ops}' -Nicks @('Simon', 'bob-other') -MachineId 'marchhare'
        $lines = @(Get-Content -LiteralPath '{ops}' | ForEach-Object {{ $_.Trim() }} | Where-Object {{ $_ }})
        $join = ($lines -join ',')
        if ($join -notmatch '(?i)bob-marchhare') {{ throw "lost local ear: $join" }}
        if ($join -notmatch '(?i)Simon') {{ throw "lost Simon: $join" }}
        if ($join -notmatch '(?i)bob-other') {{ throw "missing merged nick: $join" }}
        if ($lines.Count -eq 1 -and $lines[0] -match '\\s') {{
            throw "single space-joined line (FR #3512): $($lines[0])"
        }}
        Write-Output ('merge-ok:' + $join)
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "merge-ok:" in text

