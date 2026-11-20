"""FR #8531: Get-UpdateFleetPSCredential must return exactly one PSCredential."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from repo_layout import ROOT

SCRIPT = ROOT / "common" / "scripts" / "Update-BobFleet.ps1"
WIN = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell CredMan")


def test_source_voids_credfree_and_trims_nul():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "[void][BobUpdateFleetCredMan]::CredFree($ptr)" in src
    assert "TrimEnd([char]0)" in src
    # Unvoided CredFree in Get-UpdateFleetPSCredential finally would re-break bind.
    get_fn = src.split("function Get-UpdateFleetPSCredential", 1)[1].split("\nfunction ", 1)[0]
    assert "CredFree($ptr)" in get_fn
    assert "[void][BobUpdateFleetCredMan]::CredFree($ptr)" in get_fn
    bare = [ln for ln in get_fn.splitlines() if "CredFree($ptr)" in ln and "[void]" not in ln]
    assert bare == [], bare


@WIN
def test_credfree_bool_does_not_join_pipeline_when_voided(tmp_path: Path):
    """Mirror the Get finally pattern: voided CredFree => single return object."""
    ps1 = tmp_path / "t.ps1"
    ps1.write_text(
        r'''
$ErrorActionPreference = "Stop"
$path = "%s"
$raw = Get-Content -LiteralPath $path -Raw
$idx = $raw.IndexOf("# --- main ---")
if ($idx -lt 0) { throw "no main marker" }
. ([scriptblock]::Create($raw.Substring(0, $idx)))
Ensure-UpdateFleetCredManType
function Demo-Voided {
    try { return "cred-only" }
    finally { [void][BobUpdateFleetCredMan]::CredFree([IntPtr]::Zero) }
}
function Demo-Leaky {
    try { return "cred-plus-bool" }
    finally {
        try { [BobUpdateFleetCredMan]::CredFree([IntPtr]::Zero) } catch {}
    }
}
$voided = @(Demo-Voided)
$leaky = @(Demo-Leaky)
"VOID_COUNT=$($voided.Count)"
"LEAK_COUNT=$($leaky.Count)"
"LEAK_HAS_BOOL=$($leaky | Where-Object { $_ -is [bool] } | Measure-Object | Select-Object -ExpandProperty Count)"
'''
        % str(SCRIPT).replace("\\", "\\\\"),
        encoding="utf-8-sig",
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert "VOID_COUNT=1" in out
    assert "LEAK_COUNT=2" in out
    assert "LEAK_HAS_BOOL=1" in out
