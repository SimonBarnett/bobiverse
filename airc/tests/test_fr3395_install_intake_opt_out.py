"""FR #3395: Install-Airc failure intake respects crash-report opt-out and passes -Repo."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
REPORT = ROOT / "common/scripts/Report-BobiverseIntakeIssue.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _ps(script: str, env: dict | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def test_fr3395_common_helper_exists():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "function Test-BobiverseCrashReportAllowsIntake" in t
    assert "FR #3395" in t


def test_fr3395_install_gates_intake_and_passes_repo():
    t = INSTALL.read_text(encoding="utf-8-sig")
    common = COMMON.read_text(encoding="utf-8-sig")
    # FR #3515 moved the gate into Send-BobiverseAircInstallFailureIntake (still FR #3395 policy).
    assert "Send-BobiverseAircInstallFailureIntake" in t or "Test-BobiverseCrashReportAllowsIntake" in t
    assert "Test-BobiverseCrashReportAllowsIntake" in common
    assert "SimonBarnett/bobiverse" in common or "SimonBarnett/bobiverse" in t
    assert "Report-BobiverseIntakeIssue" in common or "Report-BobiverseIntakeIssue" in t
    # Must not call report without -Repo anymore.
    assert "-Repo" in common or "Repo = 'SimonBarnett/bobiverse'" in common or "Repo SimonBarnett/bobiverse" in t


def test_fr3395_report_honours_opt_out_for_airc_installroot():
    t = REPORT.read_text(encoding="utf-8-sig")
    assert "FR #3395" in t
    assert "Test-BobiverseCrashReportAllowsIntake" in t or "crash-report" in t.lower()


def test_fr3395_docs_mention_opt_out():
    blob = POST.read_text(encoding="utf-8") + "\n" + SKILL.read_text(encoding="utf-8")
    assert "3395" in blob


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3395_helper_false_when_config_disabled(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOBIVERSE_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "crash-report.json").write_text(
        json.dumps({"enabled": False, "mode": "off"}), encoding="utf-8"
    )
    (cfg / "airc.json").write_text(json.dumps({"shell_mode": "off"}), encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        if (Test-BobiverseCrashReportAllowsIntake -InstallRoot '{root}') {{
            throw 'expected false when enabled=false'
        }}
        Write-Output 'deny-ok'
        """
    )
    proc = _ps(script, env={"BOB_CRASH_REPORT": "", "BOBIVERSE_CRASH_REPORT": ""})
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "deny-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3395_helper_true_when_config_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "crash-report.json").write_text(
        json.dumps({"enabled": True, "mode": "full"}), encoding="utf-8"
    )
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        if (-not (Test-BobiverseCrashReportAllowsIntake -InstallRoot '{root}')) {{
            throw 'expected true when enabled=true'
        }}
        Write-Output 'allow-ok'
        """
    )
    proc = _ps(script, env={"BOB_CRASH_REPORT": "", "BOBIVERSE_CRASH_REPORT": ""})
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "allow-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3395_report_skips_http_when_opt_out(tmp_path: Path, monkeypatch):
    """enabled=false + airc InstallRoot => no POST (IntakeUrl would fail if hit)."""
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "crash-report.json").write_text(
        json.dumps({"enabled": False, "mode": "local-only"}), encoding="utf-8"
    )
    (cfg / "airc.json").write_text("{}", encoding="utf-8")
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    # FR #3554: never touch live C:\ProgramData\Bobiverse during pytest log writes.
    pd = tmp_path / "ProgramDataBobiverse"
    pd.mkdir()
    # Port 9 / blackhole URL - connection would fail if Report ignored opt-out.
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        $r = & '{REPORT}' -Title 'airc install: Install-AircConsole failed' `
            -Body 'boom-fr3395' -Repo 'SimonBarnett/bobiverse' `
            -InstallRoot '{root}' -OutboxDir '{outbox}' `
            -IntakeUrl 'http://127.0.0.1:9/fr3395-should-not-hit' -TimeoutSec 2
        if ($r.skipped_crash_opt_out -ne $true) {{
            throw ("expected skipped_crash_opt_out; got " + ($r | ConvertTo-Json -Compress))
        }}
        Write-Output 'report-skip-ok'
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
    assert "report-skip-ok" in (proc.stdout or "")
    # Must not have queued a network-failure outbox from a real POST attempt.
    assert not list(outbox.glob("report-*.json"))


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell")
def test_fr3395_report_dryrun_posts_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "crash-report.json").write_text(
        json.dumps({"enabled": True, "mode": "full"}), encoding="utf-8"
    )
    (cfg / "airc.json").write_text("{}", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        $r = & '{REPORT}' -Title 'airc install: Install-AircConsole failed' `
            -Body 'boom-fr3395-on' -Repo 'SimonBarnett/bobiverse' `
            -InstallRoot '{root}' -DryRun
        if ($r.dry_run -ne $true) {{ throw 'expected dry_run' }}
        if ($r.repo -ne 'SimonBarnett/bobiverse') {{ throw 'repo missing' }}
        if ($r.skipped_crash_opt_out) {{ throw 'should not skip when enabled' }}
        Write-Output 'report-dryrun-ok'
        """
    )
    proc = _ps(script, env={"BOB_CRASH_REPORT": "", "BOBIVERSE_CRASH_REPORT": ""})
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "report-dryrun-ok" in (proc.stdout or "")


def test_mrb3440_install_fail_closed_on_policy_error():
    # FR #3515: fail-closed lives in Send-BobiverseAircInstallFailureIntake (Common).
    common = COMMON.read_text(encoding="utf-8")
    install = INSTALL.read_text(encoding="utf-8")
    blob = common + "\n" + install
    assert "$allowIntake = $false" in common
    assert "catch { $allowIntake = $true }" not in blob
    assert "policy check failed" in blob.lower() or "skip intake" in blob.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_mrb3440_corrupt_crash_report_json_denies_intake(tmp_path: Path):
    root = tmp_path / "airc"
    cfg = root / "config"
    cfg.mkdir(parents=True)
    (cfg / "crash-report.json").write_text("{not-json", encoding="utf-8")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $ok = Test-BobiverseCrashReportAllowsIntake -InstallRoot '{root}'
        if ($ok) {{ throw 'corrupt json must deny intake' }}
        Write-Output 'corrupt-deny-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "corrupt-deny-ok" in (proc.stdout or "")


def test_mrb3440_report_defaults_deny_until_policy_allows():
    t = REPORT.read_text(encoding="utf-8-sig")
    assert "MRB #3440" in t
    assert "$allow = $false" in t

