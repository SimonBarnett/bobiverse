"""FR #3685: Install-Airc.cmd propagates powershell exit; outer fail report; RunInstall Return=check.

When Install-Airc.ps1 never runs (#Requires refuse / parse error), the .cmd must still:
1. exit /b with the real ERRORLEVEL (so CAQuietExec + Return=check => msiexec 1603)
2. append a failure line to ProgramData\\Bobiverse\\logs\\install-airc.log
3. send one redacted intake report (unless BOBIVERSE_CRASH_REPORT=off)
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

CMD = ROOT / "airc/scripts/Install-Airc.cmd"
REPORTER = ROOT / "airc/scripts/Report-AircInstallCmdFailure.ps1"
PACK = ROOT / "common/scripts/Pack-BobiverseRelease.ps1"
COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
ALLOW = "Get-BobiverseAircClientAllowedScriptNames"


def test_fr3685_cmd_captures_errorlevel_and_calls_outer_reporter():
    t = CMD.read_text(encoding="utf-8")
    assert "FR #3685" in t or "3685" in t
    assert "set \"EC=%ERRORLEVEL%\"" in t or "set EC=%ERRORLEVEL%" in t
    assert "exit /b %EC%" in t
    assert "install-airc.log" in t
    assert "Report-AircInstallCmdFailure.ps1" in t
    # Must not rely only on bare exit /b %ERRORLEVEL% after other commands without capture.
    assert "ERRORLEVEL" in t


def test_fr3685_pack_runinstall_return_check_and_cmd_call_wrap():
    p = PACK.read_text(encoding="utf-8-sig")
    assert 'Id="RunInstall"' in p
    assert 'Return="check"' in p
    # CAQuietExec must invoke via quoted System64Folder cmd /c call (FR #3685 + #3741).
    assert "&quot;[System64Folder]cmd.exe&quot; /d /c call" in p
    assert "FR #3685" in p or "3685" in p
    assert "FR #3741" in p or "3741" in p


def test_fr3685_outer_reporter_exists_no_requires_51():
    assert REPORTER.is_file(), "Report-AircInstallCmdFailure.ps1 required beside Install-Airc.cmd"
    t = REPORTER.read_text(encoding="utf-8")
    # Comment may mention #Requires; the directive itself must be absent.
    assert not any(
        ln.strip().startswith("#Requires") for ln in t.splitlines()
    ), "outer reporter must run when Install-Airc.ps1 #Requires refuses"
    assert "BOBIVERSE_CRASH_REPORT" in t or "BOB_CRASH_REPORT" in t
    assert "Redact" in t or "redact" in t
    assert "SimonBarnett/bobiverse" in t
    assert "profile" in t.lower()


def test_fr3685_client_allowlist_keeps_outer_reporter():
    common = COMMON.read_text(encoding="utf-8-sig")
    assert ALLOW in common
    assert "Report-AircInstallCmdFailure.ps1" in common


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd + powershell")
def test_fr3685_cmd_stub_powershell_exit1_returns1_and_reports_once(tmp_path: Path, monkeypatch):
    """Stub install/unblock powershell returning 1: .cmd exits 1, logs, reporter once; opt-out => 0."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log_root = tmp_path / "ProgramData" / "Bobiverse" / "logs"
    log_root.mkdir(parents=True)

    stub = tmp_path / "ps-fail.cmd"
    stub.write_text("@echo off\r\nexit /b 1\r\n", encoding="ascii")
    stub_q = str(stub)

    # Copy production .cmd but point Unblock + Install-Airc.ps1 lines at the failing stub.
    # Keep the Report-AircInstallCmdFailure line on real powershell.exe.
    raw = CMD.read_text(encoding="utf-8")
    out_lines = []
    for line in raw.splitlines():
        if "Install-Airc.ps1" in line or "Unblock-File" in line:
            # .cmd stubs need CALL or control never returns to Install-Airc.cmd.
            out_lines.append(
                line.replace("powershell.exe", f'call "{stub_q}"')
            )
        else:
            out_lines.append(line)
    (scripts / "Install-Airc.cmd").write_text("\r\n".join(out_lines) + "\r\n", encoding="ascii")

    counter = tmp_path / "report-count.txt"
    (scripts / "Report-AircInstallCmdFailure.ps1").write_text(
        textwrap.dedent(
            f"""
            param(
              [int]$ExitCode = 1,
              [string]$ScriptsDir = '',
              [string]$ArgsText = '',
              [string]$InstallRoot = '',
              [string]$Profile = '',
              [string]$IntakeUrl = '',
              [switch]$DryRun
            )
            $c = '{counter}'
            $n = 0
            if (Test-Path -LiteralPath $c) {{ $n = [int](Get-Content -LiteralPath $c -Raw).Trim() }}
            $n++
            Set-Content -LiteralPath $c -Value $n -Encoding ASCII
            $raw = [string]$env:BOBIVERSE_CRASH_REPORT
            if (-not $raw) {{ $raw = [string]$env:BOB_CRASH_REPORT }}
            if ($raw -match '^(?i)0|off|false|no|local-only|local_only|spool$') {{
              Set-Content -LiteralPath $c -Value 0 -Encoding ASCII
            }}
            exit 0
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["ProgramData"] = str(tmp_path / "ProgramData")
    monkeypatch.delenv("BOB_CRASH_REPORT", raising=False)
    monkeypatch.delenv("BOBIVERSE_CRASH_REPORT", raising=False)
    env.pop("BOB_CRASH_REPORT", None)
    env.pop("BOBIVERSE_CRASH_REPORT", None)

    proc = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "call",
            str(scripts / "Install-Airc.cmd"),
            "-InstallRoot",
            str(tmp_path / "airc"),
            "-Profile",
            "client",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(scripts),
        timeout=60,
    )
    assert proc.returncode == 1, (proc.stdout or "") + (proc.stderr or "")
    log = log_root / "install-airc.log"
    assert log.is_file(), "install-airc.log must exist when ps1 never ran"
    log_txt = log.read_text(encoding="utf-8", errors="replace")
    assert "FAIL" in log_txt or "exit=" in log_txt
    assert counter.is_file(), "outer reporter must run"
    assert counter.read_text(encoding="ascii").strip() == "1"

    counter.write_text("0", encoding="ascii")
    env["BOBIVERSE_CRASH_REPORT"] = "off"
    flag = log_root / "install-airc-fail-reported.flag"
    if flag.exists():
        flag.unlink()
    proc2 = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            "call",
            str(scripts / "Install-Airc.cmd"),
            "-InstallRoot",
            str(tmp_path / "airc"),
            "-Profile",
            "client",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(scripts),
        timeout=60,
    )
    assert proc2.returncode == 1
    assert counter.read_text(encoding="ascii").strip() == "0"
