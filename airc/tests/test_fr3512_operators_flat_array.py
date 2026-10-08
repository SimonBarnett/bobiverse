"""FR #3512: Merge defensive nick split + Install flatten (absorbed into #3513/#3557)."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"


def _ps(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(ROOT),
    )


def test_fr3512_resolve_uses_noenumerate():
    t = COMMON.read_text(encoding="utf-8-sig")
    i = t.find("function Resolve-BobiverseAircOperatorNicks")
    assert i > 0
    chunk = t[i : i + 2200]
    assert "FR #3512" in chunk
    assert "NoEnumerate" in chunk


def test_fr3512_merge_has_defensive_split():
    t = COMMON.read_text(encoding="utf-8-sig")
    j = t.find("function Merge-BobiverseAircOperatorsFile")
    assert j > 0
    merge = t[j : j + 2800]
    assert "FR #3512" in merge
    assert r"[,;\s]+" in merge
    assert "System.Array" in merge


def test_fr3512_install_flattens_resolve_result():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3512" in t
    assert "Resolve-BobiverseAircOperatorNicks" in t
    assert "flatOps" in t
    assert "System.Array" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3512_nested_array_merge_splits_defensively(tmp_path: Path):
    """Nested @() nick array must not become one space-joined operators.txt line."""
    ops = tmp_path / "operators-buggy.txt"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $inner = [string[]]@('Simon','bob-win-mpre8vi4u6u')
        $Operators = @(,$inner)
        Merge-BobiverseAircOperatorsFile -Path '{ops}' -Nicks $Operators -MachineId 'marchhare' -NoEnsureBobLocal | Out-Null
        $lines = @(Get-Content -LiteralPath '{ops}' | Where-Object {{ $_ }})
        if ($lines.Count -eq 1 -and $lines[0] -match '\\s') {{
          throw ('REGRESSION nested nick line: ' + $lines[0])
        }}
        if ($lines -notcontains 'Simon') {{ throw 'missing Simon after defensive split' }}
        if ($lines -notcontains 'bob-win-mpre8vi4u6u') {{ throw 'missing bob-win-mpre8vi4u6u after defensive split' }}
        Write-Output 'defensive-merge-ok'
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "defensive-merge-ok" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3512_install_flatten_writes_one_nick_per_line(tmp_path: Path):
    """Install-Airc flatten path: Resolve then flatOps then Merge -> distinct lines."""
    ops = tmp_path / "operators.txt"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $Operators = @('Simon')
        $OperatorsExtra = 'bob-win-mpre8vi4u6u'
        $resolvedOps = Resolve-BobiverseAircOperatorNicks -Profile 'fleet' -Operators $Operators -OperatorsExtra $OperatorsExtra
        $flatOps = New-Object System.Collections.Generic.List[string]
        foreach ($item in @($resolvedOps)) {{
          if ($null -eq $item) {{ continue }}
          if (($item -is [System.Array]) -and -not ($item -is [string])) {{
            foreach ($n in $item) {{
              foreach ($p in @(([string]$n) -split '[,;\\s]+' | Where-Object {{ $_ }})) {{
                [void]$flatOps.Add($p.Trim())
              }}
            }}
          }} else {{
            foreach ($p in @(([string]$item) -split '[,;\\s]+' | Where-Object {{ $_ }})) {{
              [void]$flatOps.Add($p.Trim())
            }}
          }}
        }}
        $Operators = [string[]]$flatOps.ToArray()
        if ($Operators.Count -lt 2) {{ throw ('expected flat Count>=2 got ' + $Operators.Count + ' [' + ($Operators -join '|') + ']') }}
        foreach ($n in $Operators) {{
          if ($n -match '\\s') {{ throw ('nick still contains space: [' + $n + ']') }}
        }}
        Merge-BobiverseAircOperatorsFile -Path '{ops}' -Nicks $Operators -MachineId 'marchhare' | Out-Null
        $lines = @(Get-Content -LiteralPath '{ops}' | Where-Object {{ $_ -and $_ -notmatch '^#' }})
        if ($lines -notcontains 'Simon') {{ throw 'missing Simon' }}
        if ($lines -notcontains 'bob-win-mpre8vi4u6u') {{ throw 'missing bob-win-mpre8vi4u6u' }}
        if ($lines -notcontains 'bob-marchhare') {{ throw 'missing bob-marchhare' }}
        $joined = @($lines | Where-Object {{ $_ -match '\\s' }})
        if ($joined.Count -gt 0) {{ throw ('space-joined line still present: ' + ($joined -join ' ;; ')) }}
        Write-Output ('lines=' + ($lines -join ','))
        Write-Output 'fr3512-ok'
        """
    )
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3512" in inst
    assert "flatOps" in inst

    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "fr3512-ok" in text
    assert "bob-win-mpre8vi4u6u" in text
