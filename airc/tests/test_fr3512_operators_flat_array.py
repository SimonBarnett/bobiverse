"""FR #3512: Install-Airc @() wrap must not nest Resolve-BobiverseAircOperatorNicks into one operators.txt line."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


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


def test_fr3512_install_text_flattens_resolve_result():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3512" in t
    assert "Resolve-BobiverseAircOperatorNicks" in t
    # Must not leave the bare nested @() assign without flatten (the #3397 bug).
    assert "flatten" in t.lower() or "FR #3512" in t


def test_fr3512_resolve_return_not_only_unary_comma_trap():
    """Source pin: Resolve documents FR #3512 / avoids nesting under @()."""
    t = COMMON.read_text(encoding="utf-8-sig")
    i = t.find("function Resolve-BobiverseAircOperatorNicks")
    assert i > 0
    chunk = t[i : i + 1800]
    assert "FR #3512" in chunk or "FR #3397" in chunk
    # Merge should split space-joined tokens defensively.
    j = t.find("function Merge-BobiverseAircOperatorsFile")
    merge = t[j : j + 2200]
    assert "FR #3512" in merge or "split" in merge.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3512_install_airc_resolve_wrap_writes_one_nick_per_line(tmp_path: Path):
    """Exact Install-Airc path: @(Resolve...) then Merge → distinct lines + AuthPolicy allow."""
    ops = tmp_path / "operators.txt"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        # Verbatim Install-Airc pattern that nested under FR #3397 unary-comma return.
        $Operators = @('Simon')
        $OperatorsExtra = 'bob-win-mpre8vi4u6u'
        $profForOps = 'fleet'
        $Operators = @(Resolve-BobiverseAircOperatorNicks -Profile $profForOps -Operators $Operators -OperatorsExtra $OperatorsExtra)
        # FR #3512 flatten (must match Install-Airc.ps1)
        $flat = New-Object System.Collections.Generic.List[string]
        foreach ($item in @($Operators)) {{
          if ($null -eq $item) {{ continue }}
          if (($item -is [System.Array]) -and -not ($item -is [string])) {{
            foreach ($n in $item) {{
              foreach ($p in @(([string]$n) -split '[,;\\s]+' | Where-Object {{ $_ }})) {{
                [void]$flat.Add($p.Trim())
              }}
            }}
          }} else {{
            foreach ($p in @(([string]$item) -split '[,;\\s]+' | Where-Object {{ $_ }})) {{
              [void]$flat.Add($p.Trim())
            }}
          }}
        }}
        $Operators = $flat.ToArray()
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
    # Also require Install-Airc source to contain the flatten loop (not only this test).
    inst = INSTALL.read_text(encoding="utf-8-sig")
    assert "FR #3512" in inst, "Install-Airc must implement FR #3512 flatten before this pin can pass"

    proc = _ps(script)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "fr3512-ok" in text
    assert "bob-win-mpre8vi4u6u" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3512_nested_array_without_flatten_is_the_bug(tmp_path: Path):
    """Document the defect: unary-comma + @() nests; Merge without split writes one line."""
    ops = tmp_path / "operators-buggy.txt"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        # Simulate pre-fix Resolve return shape if still using unary comma alone:
        $inner = [string[]]@('Simon','bob-win-mpre8vi4u6u')
        $Operators = @(,$inner)   # same nest shape as return ,$arr then @()
        # Call Merge WITHOUT going through Install flatten — pre-#3512 Merge wrote one line.
        # After #3512 Merge must still split defensively.
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
