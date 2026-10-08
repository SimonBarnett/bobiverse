"""FR #3515: client install-failure intake kept after purge + redacted; outer catch reports."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
REPORT = ROOT / "common/scripts/Report-BobiverseIntakeIssue.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


def _ps(script: str, env: dict | None = None, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    if env:
        e.update(env)
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
        env=e,
    )


def test_fr3515_source_pins_helper_outer_catch_and_redact():
    common = COMMON.read_text(encoding="utf-8-sig")
    install = INSTALL.read_text(encoding="utf-8-sig")
    assert "function Redact-BobiverseCrashText" in common
    assert "function Send-BobiverseAircInstallFailureIntake" in common
    assert "FR #3515" in common
    assert "Send-BobiverseAircInstallFailureIntake" in install
    assert "install-fail" in install
    skill = SKILL.read_text(encoding="utf-8")
    assert "3515" in skill


def test_fr3515_client_allowlist_still_keeps_report_script():
    common = COMMON.read_text(encoding="utf-8-sig")
    assert "'Report-BobiverseIntakeIssue.ps1'" in common
    assert "Get-BobiverseAircClientAllowedScriptNames" in common


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3515_redact_mirrors_crash_shapes():
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $cases = @(
            @('Authorization: Bearer FAKEbearerVALUE123', 'FAKEbearerVALUE123'),
            @('password=FAKEpw99', 'FAKEpw99'),
            @('https://user:FAKEurlpw@host/x', 'FAKEurlpw'),
            @('PASS FAKEircserverpw', 'FAKEircserverpw'),
            @('ghp_abcdefghijklmnopqrstuvwxyz0123456789', 'ghp_abcdefghijklmnopqrstuvwxyz0123456789')
        )
        foreach ($c in $cases) {{
            $out = Redact-BobiverseCrashText -Text $c[0]
            if ($out -match [regex]::Escape($c[1])) {{ throw ("still contains secret: " + $c[1] + " in " + $out) }}
            if ($out -notmatch 'redacted') {{ throw ("no redaction marker: " + $out) }}
        }}
        Write-Output 'redact-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "redact-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3515_client_purge_keeps_report_and_send_dryrun_redacts(tmp_path: Path, monkeypatch):
    """Client allow-list purge leaves Report script; Send redacts + DryRun when policy allows."""
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOBIVERSE_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "crash-report.json").write_text(
        json.dumps({"enabled": True, "mode": "full", "source": "client-profile"}),
        encoding="utf-8",
    )
    (root / "config" / "airc.json").write_text("{}", encoding="utf-8")
    (scripts / "Report-BobiverseIntakeIssue.ps1").write_text(
        REPORT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (scripts / "Bobiverse-Common.ps1").write_text(
        COMMON.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (scripts / "should-purge-me.ps1").write_text("# junk", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "x.md").write_text("x", encoding="utf-8")
    pd = tmp_path / "ProgramDataBobiverse"
    pd.mkdir()
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $null = Remove-BobiverseAircClientExtraPayload -InstallRoot '{root}'
        $report = Join-Path '{root}' 'scripts\\Report-BobiverseIntakeIssue.ps1'
        if (-not (Test-Path -LiteralPath $report)) {{ throw 'Report script missing after client purge' }}
        if (Test-Path -LiteralPath (Join-Path '{root}' 'docs')) {{ throw 'docs should be purged' }}
        if (Test-Path -LiteralPath (Join-Path '{root}' 'scripts\\should-purge-me.ps1')) {{ throw 'junk script should be purged' }}
        $r = Send-BobiverseAircInstallFailureIntake -InstallRoot '{root}' `
            -ScriptsDir '{root}\\scripts' `
            -Title 'airc install fail password=FAKEpw99' `
            -Body 'boom token=FAKEtok123 path=C:\\Users\\Administrator\\secret' `
            -DryRun
        if (-not $r) {{ throw 'expected result object' }}
        if ($r.skipped) {{ throw 'should not skip when enabled' }}
        if ($r.dry_run -ne $true) {{ throw 'expected dry_run' }}
        $blob = ($r.title + ' ' + $r.body)
        if ($blob -match 'FAKEpw99|FAKEtok123') {{ throw ("secrets leaked: " + $blob) }}
        if ($blob -notmatch 'redacted') {{ throw ("no redact marker: " + $blob) }}
        Write-Output 'send-dryrun-ok'
        """
    )
    proc = _ps(
        script,
        env={
            "BOB_CRASH_REPORT": "",
            "BOBIVERSE_CRASH_REPORT": "",
            "BOBIVERSE_PROGRAMDATA_ROOT": str(pd),
        },
    )
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "send-dryrun-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3515_send_zero_calls_when_opt_out(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config" / "crash-report.json").write_text(
        json.dumps({"enabled": False, "mode": "off"}), encoding="utf-8"
    )
    (root / "config" / "airc.json").write_text("{}", encoding="utf-8")
    (scripts / "Report-BobiverseIntakeIssue.ps1").write_text(
        REPORT.read_text(encoding="utf-8"), encoding="utf-8"
    )
    pd = tmp_path / "ProgramDataBobiverse"
    pd.mkdir()
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $r = Send-BobiverseAircInstallFailureIntake -InstallRoot '{root}' `
            -ScriptsDir '{root}\\scripts' `
            -Title 'airc install fail' -Body 'boom' -DryRun `
            -IntakeUrl 'http://127.0.0.1:9/fr3515-must-not-hit'
        if (-not $r.skipped) {{ throw 'expected skipped when opt-out' }}
        Write-Output 'opt-out-ok'
        """
    )
    proc = _ps(
        script,
        env={
            "BOB_CRASH_REPORT": "",
            "BOBIVERSE_CRASH_REPORT": "off",
            "BOBIVERSE_PROGRAMDATA_ROOT": str(pd),
        },
    )
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "opt-out-ok" in (proc.stdout or "")
