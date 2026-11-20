"""FR #8532: UpdateFleet classifies WinRM-closed remotes and points to tray-local/airc."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PS1 = ROOT / "common" / "scripts" / "Update-BobFleet.ps1"


def _utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fr8532_helpers_present_in_source():
    text = _utf8(PS1)
    assert "FR #8532" in text
    assert "function Test-UpdateFleetWinRmClosed" in text
    assert "function Get-UpdateFleetWinRmClosedFallback" in text
    assert "winrm-closed" in text
    assert "tray-local" in text
    assert "airc" in text.lower()
    assert "OpenTimeout" in text or "OperationTimeout" in text


def test_fr8532_synopsis_mentions_winrm_closed_fallback():
    text = _utf8(PS1)
    head = text[:3500]
    assert "WinRM" in head
    assert re.search(r"tray.?local|local.?tray|airc", head, re.I)


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell helpers")
def test_fr8532_classify_and_fallback_helpers(tmp_path: Path):
    script = tmp_path / "probe.ps1"
    # Load only the two helper function ASTs so # --- main --- never runs.
    script.write_text(
        "\n".join(
            [
                "$path = '{0}'".format(str(PS1).replace("'", "''")),
                "$tokens = $null; $errors = $null",
                "$ast = [System.Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)",
                "$want = @('Test-UpdateFleetWinRmClosed', 'Get-UpdateFleetWinRmClosedFallback')",
                "$defs = $ast.FindAll({",
                "  param($n)",
                "  $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $want -contains $n.Name",
                "}, $true)",
                "foreach ($d in $defs) { Invoke-Expression $d.Extent.Text }",
                "if (-not (Get-Command Test-UpdateFleetWinRmClosed -ErrorAction SilentlyContinue)) { throw 'helper missing' }",
                "$pairs = @(",
                "  @('WinRM cannot complete the operation', 'True'),",
                "  @('The WinRM client cannot complete the operation within the time specified', 'True'),",
                "  @('Connecting to remote server marchhare failed', 'True'),",
                "  @('Access is denied', 'False')",
                ")",
                "foreach ($p in $pairs) {",
                "  $closed = [bool](Test-UpdateFleetWinRmClosed -Message $p[0])",
                "  Write-Output ('CLOSED=' + $p[1] + '|' + $closed)",
                "}",
                "$fb = Get-UpdateFleetWinRmClosedFallback -MachineId 'marchhare'",
                "Write-Output ('METHOD=' + $fb.method)",
                "Write-Output ('FALLBACK=' + $fb.fallback)",
                "Write-Output ('HINT=' + $fb.hint)",
            ]
        ),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "CLOSED=True|True" in out
    assert "CLOSED=False|False" in out
    assert "METHOD=winrm-closed" in out
    assert "FALLBACK=tray-local" in out
    assert "marchhare" in out.lower()
    assert "updatefleet" in out.lower() or "Update-BobFleet" in out
    assert "airc" in out.lower() or "tray" in out.lower()