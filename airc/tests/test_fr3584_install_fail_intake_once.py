"""FR #3584: nested Install-AircConsole fail must not double-file intake."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"


def _ps(script: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def test_fr3584_source_sets_flag_and_outer_skips():
    t = INSTALL.read_text(encoding="utf-8-sig")
    assert "AircInstallFailReported" in t
    assert "FR #3584" in t
    assert "$script:AircInstallFailReported = $true" in t
    assert "if (-not $script:AircInstallFailReported)" in t
    assert "skip outer install-fail intake" in t
    # Nested catch still reports with the specific title.
    assert "Install-AircConsole failed" in t
    skill = SKILL.read_text(encoding="utf-8")
    assert "3584" in skill
    assert "AircInstallFailReported" in skill


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3584_nested_console_fail_reports_exactly_once():
    """Mirror Install-Airc nested catch + flag: forced console fail → one Send."""
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:SendCount = 0
        $script:SendTitles = New-Object System.Collections.Generic.List[string]
        function Send-BobiverseAircInstallFailureIntake {{
            param(
                [string]$InstallRoot = '',
                [string]$ScriptsDir = '',
                [Parameter(Mandatory)][string]$Title,
                [Parameter(Mandatory)][string]$Body,
                [string]$Repo = 'SimonBarnett/bobiverse',
                [string]$IntakeUrl = '',
                [switch]$DryRun
            )
            $script:SendCount++
            [void]$script:SendTitles.Add($Title)
            return [pscustomobject]@{{ dry_run = $true; skipped = $false; title = $Title; body = $Body }}
        }}
        $script:AircInstallFailReported = $false
        $script:AircInstallOk = $false
        try {{
            try {{
                throw 'forced Install-AircConsole boom'
            }} catch {{
                $script:AircInstallFailReported = $true
                try {{
                    [void](Send-BobiverseAircInstallFailureIntake -InstallRoot 'X' -ScriptsDir 'X' `
                        -Title 'airc install: Install-AircConsole failed' `
                        -Body $_.Exception.Message -DryRun)
                }} catch {{ }}
                throw
            }}
            # Protect / Start would be here on success path
        }} catch {{
            if (-not $script:AircInstallFailReported) {{
                try {{
                    [void](Send-BobiverseAircInstallFailureIntake -InstallRoot 'X' -ScriptsDir 'X' `
                        -Title 'airc install: Install-Airc failed' `
                        -Body $_.Exception.Message -DryRun)
                    $script:AircInstallFailReported = $true
                }} catch {{ }}
            }}
        }}
        if ($script:SendCount -ne 1) {{
            throw ("expected exactly 1 Send, got " + $script:SendCount + " titles=" + ($script:SendTitles -join ';'))
        }}
        if ($script:SendTitles[0] -notmatch 'Install-AircConsole failed') {{
            throw ("expected console-specific title, got " + $script:SendTitles[0])
        }}
        Write-Output 'once-ok'
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "once-ok" in text


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3584_outer_only_fail_still_reports_once():
    """Protect/Start-style outer-only failure still files exactly one intake."""
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:SendCount = 0
        function Send-BobiverseAircInstallFailureIntake {{
            param(
                [string]$InstallRoot = '',
                [string]$ScriptsDir = '',
                [Parameter(Mandatory)][string]$Title,
                [Parameter(Mandatory)][string]$Body,
                [string]$Repo = 'SimonBarnett/bobiverse',
                [string]$IntakeUrl = '',
                [switch]$DryRun
            )
            $script:SendCount++
            return [pscustomobject]@{{ dry_run = $true; skipped = $false; title = $Title; body = $Body }}
        }}
        $script:AircInstallFailReported = $false
        try {{
            # console succeeded; Protect fails
            throw 'forced Protect FailClosed boom'
        }} catch {{
            if (-not $script:AircInstallFailReported) {{
                [void](Send-BobiverseAircInstallFailureIntake -InstallRoot 'X' -ScriptsDir 'X' `
                    -Title 'airc install: Install-Airc failed' `
                    -Body $_.Exception.Message -DryRun)
                $script:AircInstallFailReported = $true
            }}
        }}
        if ($script:SendCount -ne 1) {{ throw ("expected 1 Send, got " + $script:SendCount) }}
        Write-Output 'outer-once-ok'
        """
    )
    proc = _ps(script)
    text = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "outer-once-ok" in text
