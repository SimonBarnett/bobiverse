"""FR #5876: local MSI fixtures must not file live UPDATE failures."""
from __future__ import annotations

import hashlib
import shutil
import subprocess

import pytest

from repo_layout import ROOT

UPD = ROOT / "common/scripts/Update-BobiverseService.ps1"
PS = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")


def test_reported_checksum_matches_airc_test_fixture():
    assert hashlib.sha256(b"not-an-msi").hexdigest() == (
        "9e3df49fea44e4979294ac1012be63caf35074da0c74eed4de2873f7b4ed5710"
    )
    source = (ROOT / "airc/tests/test_fr77_update_detached.py").read_text(encoding="utf-8")
    start = source.index("def test_fake_release_target_version_allowlist_and_hash")
    end = source.index("def test_loop_guard_and_pending_for_airc_product", start)
    fixture = source[start:end]
    assert 'monkeypatch.setenv("BOB_CRASH_REPORT", "local-only")' in fixture
    assert 'monkeypatch.setenv("BOBIVERSE_CRASH_REPORT", "local-only")' in fixture


def test_all_updater_intake_calls_include_local_asset_hook():
    source = UPD.read_text(encoding="utf-8")
    gates = [line for line in source.splitlines() if "$intakeDry =" in line]
    assert len(gates) == source.count("-DryRun:$intakeDry") == 3
    assert all("[bool]$AllowLocalAssets" in line for line in gates)


@pytest.mark.skipif(not PS, reason="needs PowerShell")
@pytest.mark.parametrize("hook", ["", "DryRun", "ReleaseJson", "ReleaseListJson", "AllowLocalAssets"])
@pytest.mark.parametrize("function", ["Set-Failure", "Write-CheckFailIntake"])
def test_failure_intake_hooks_preserve_state_and_live_reporting(tmp_path, hook, function):
    source = UPD.read_text(encoding="utf-8")
    functions = source[source.index("function Set-Failure") : source.index("function Ensure-ServiceRunning")]
    assignment = ""
    if hook:
        value = "$true" if hook in ("DryRun", "AllowLocalAssets") else "'fixture.json'"
        assignment = f"${hook} = {value}"
    script = f"""
    $ErrorActionPreference = 'Stop'
    Set-StrictMode -Version Latest
    $Product = 'airc'
    $InstallRoot = ''
    $DryRun = $false
    $ReleaseJson = ''
    $ReleaseListJson = ''
    $AllowLocalAssets = $false
    $script:state = @{{failures=@{{}}; pending='scheduled'}}
    $script:calls = 0
    $script:saved = $false
    function Get-State {{ return $script:state }}
    function Save-State($st) {{ $script:saved = $true }}
    function Write-UpdLog($msg) {{ throw $msg }}
    function Send-BobiverseUpdateFailureIntake {{
        param($Product, $Tag, $Result, $Detail, $InstallRoot, [switch]$DryRun)
        $script:calls++
        $script:intakeDry = [bool]$DryRun
        $script:result = $Result
        $script:detail = $Detail
    }}
    {functions}
    {assignment}
    {function} -Tag 'v0.1.17' -Result 'sha256-mismatch' -Detail 'fixture mismatch'
    if ($script:calls -ne 1) {{ throw 'intake call missing' }}
    if ($script:intakeDry -ne ${'true' if hook else 'false'}) {{ throw 'wrong intake mode' }}
    if ($script:result -ne 'sha256-mismatch' -or $script:detail -ne 'fixture mismatch') {{ throw 'failure detail lost' }}
    if ('{function}' -eq 'Set-Failure') {{
        if (-not $script:saved -or $script:state.failures['v0.1.17'] -ne 1) {{ throw 'failure count lost' }}
        if ($null -ne $script:state.pending -or $script:state.lastResult -ne 'sha256-mismatch') {{ throw 'failure state lost' }}
    }}
    """
    path = tmp_path / "intake.ps1"
    path.write_text(script, encoding="utf-8")
    proc = subprocess.run(
        [PS, "-NoProfile", "-NonInteractive", "-File", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
