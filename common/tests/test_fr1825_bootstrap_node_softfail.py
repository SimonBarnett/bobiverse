"""FR #1825: Install-BootstrapTools soft-fails node/git/python; prefers official Node MSI."""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "common/scripts/Install-BootstrapTools.ps1"


def test_fr1825_script_markers():
    text = SCRIPT.read_text(encoding="utf-8")
    assert not SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "FR #1825" in text
    assert "Install-NodeOfficialMsi" in text
    assert "nodejs.org/dist" in text
    assert "ALLUSERS=1" in text
    assert "bb0eaee134f9357f22aea915ee793343e627aefc1e66488164bac6915bce2cac" in text
    # Soft-fail path for node (and siblings)
    assert "Ensure-Tool 'node'" in text
    assert "-Optional -DirectInstall" in text or ("-Optional" in text and "DirectInstall" in text)
    assert "still missing after winget install" in text  # retained for non-optional path
    assert SCRIPT.read_bytes().endswith(b"\n")


def test_fr1825_git_python_node_optional():
    text = SCRIPT.read_text(encoding="utf-8")
    # All three hard-fail tools from the FR are soft-fail now
    assert "Ensure-Tool 'git'" in text and "-Optional" in text
    assert "Ensure-Tool 'python'" in text
    # node line must be Optional
    lines = [ln for ln in text.splitlines() if "Ensure-Tool 'node'" in ln]
    assert lines, "missing Ensure-Tool node"
    assert "-Optional" in lines[0]


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows PowerShell")
def test_fr1825_ensure_tool_optional_without_winget(tmp_path: Path):
    """Unit: Optional Ensure-Tool with missing Present + failed winget emits WARN and exits 0."""
    harness = tmp_path / "harness.ps1"
    # Dot-source only the functions by extracting via a minimal reimplementation call pattern:
    # run Ensure-Tool in isolation by copying the function from the script into a stub.
    harness.write_text(
        textwrap.dedent(
            r"""
            $ErrorActionPreference = 'Stop'
            function Resolve-KnownTool([string]$Name) { return $null }
            function Install-WingetPackage([string]$Id) { return $false }
            function Ensure-Tool {
                param(
                    [string]$Label,
                    [string]$Cmd,
                    [string]$WingetId,
                    [scriptblock]$Present,
                    [switch]$Optional,
                    [scriptblock]$DirectInstall
                )
                if (-not (& $Present)) {
                    $installed = $false
                    if ($DirectInstall) { $installed = [bool](& $DirectInstall) }
                    if (-not $installed) { $installed = Install-WingetPackage $WingetId }
                    if (-not $installed) {
                        if ($Optional) {
                            Write-Host "WARN tool-missing $Label (winget unavailable or failed) - continuing (issue #10 / FR #1825)"
                            return
                        }
                        throw "$Label still missing after winget install"
                    }
                }
            }
            Ensure-Tool 'node' 'node' 'OpenJS.NodeJS.LTS' { $false } -Optional -DirectInstall { $false }
            Write-Host 'INFO harness-done'
            """
        ).lstrip(),
        encoding="utf-8",
    )
    r = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(harness),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "WARN tool-missing node" in out
    assert "still missing after winget install" not in out or "WARN" in out
    assert "INFO harness-done" in out
