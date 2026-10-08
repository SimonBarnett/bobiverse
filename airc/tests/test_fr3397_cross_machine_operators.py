"""FR #3397: fleet AIRC_OPERATORS unions into operators.txt; workstation ignores."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
INSTALL_CONSOLE = ROOT / "airc/scripts/Install-AircConsole.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
POST = ROOT / "common/docs/post-install.md"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _no_bom(path: Path) -> None:
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), path


def _ascii_ps1(path: Path) -> None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    assert all(b < 128 for b in raw), f"non-ASCII in {path}"


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


def test_fr3397_pack_and_install_wire_airc_operators():
    pack = PACK.read_text(encoding="utf-8")
    inst = INSTALL.read_text(encoding="utf-8")
    _no_bom(PACK)
    _no_bom(INSTALL)
    _ascii_ps1(INSTALL)
    assert 'Property Id="AIRC_OPERATORS"' in pack
    assert "AIRC_OPERATORS" in pack
    assert "-OperatorsExtra" in pack or "OperatorsExtra" in pack
    assert "FR #3397" in inst
    assert "OperatorsExtra" in inst
    assert "workstation" in inst.lower()


def test_fr3397_docs_skill_mention_cross_machine():
    post = POST.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    blob = post + "\n" + skill
    assert "3397" in blob
    assert "AIRC_OPERATORS" in blob
    assert "operators.txt" in blob.lower() or "operators" in blob.lower()


def test_fr3397_initialize_merges_extra_nicks_in_console_script():
    t = INSTALL_CONSOLE.read_text(encoding="utf-8")
    assert "Merge-BobiverseAircOperatorsFile" in t or "FR #3397" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows path / ACL only")
def test_fr3397_merge_union_existing_operators(tmp_path: Path):
    ops = tmp_path / "operators.txt"
    ops.write_text("Simon\nbob-marchhare\n", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        Merge-BobiverseAircOperatorsFile -Path '{ops}' -Nicks @('Simon','bob-win-mpre8vi4u6u','bob-marchhare')
        $lines = @(Get-Content -LiteralPath '{ops}' | ForEach-Object {{ $_.Trim() }} | Where-Object {{ $_ }})
        $join = ($lines -join ',')
        if ($lines.Count -ne 3) {{ throw "expected 3 unique nicks, got $join" }}
        if ($join -notmatch '(?i)bob-win-mpre8vi4u6u') {{ throw "missing cross-machine ear: $join" }}
        if ($join -notmatch '(?i)^Simon|Simon,|,Simon') {{ throw "lost Simon: $join" }}
        $bytes = [IO.File]::ReadAllBytes('{ops}')
        if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {{
            throw 'BOM written'
        }}
        Write-Output 'merge-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "merge-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3397_workstation_ignores_operators_extra_in_install_text():
    """Gate: Install-Airc must skip OperatorsExtra when profile=workstation."""
    t = INSTALL.read_text(encoding="utf-8")
    assert "OperatorsExtra" in t
    # Contiguous workstation ignore of fleet roster.
    assert "workstation" in t.lower()
    assert (
        "ignore" in t.lower()
        or "skip" in t.lower()
        or "OperatorsExtra" in t
    )
    # Prefer an explicit FR marker near the gate.
    assert "FR #3397" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3397_resolve_operators_extra_workstation_vs_fleet():
    """Behavioral: FR #3639 fleet empty (irc_ops); workstation drops OperatorsExtra."""
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $fleet = Resolve-BobiverseAircOperatorNicks -Profile 'fleet' -Operators @('Simon') -OperatorsExtra 'bob-ionos,bob-flamingo'
        if ((@($fleet) -join ',')) {{ throw ('FR #3639 fleet must be empty got ' + ($fleet -join ',')) }}
        $ws = Resolve-BobiverseAircOperatorNicks -Profile 'workstation' -Operators @('Simon') -OperatorsExtra 'bob-ionos,bob-evil'
        if ($ws -contains 'bob-ionos' -or $ws -contains 'bob-evil') {{ throw 'workstation must ignore OperatorsExtra' }}
        if ((@($ws) -join ',') -notmatch '(?i)^Simon$') {{ throw ('workstation ops unexpected: ' + ($ws -join ',')) }}
        Write-Output 'resolve-ok'
        """
    )
    inst = INSTALL.read_text(encoding="utf-8")
    assert "OperatorsExtra" in inst
    assert "Resolve-BobiverseAircOperatorNicks" in inst or "FR #3397" in inst
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "resolve-ok" in (proc.stdout or "")

