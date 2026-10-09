"""FR #3759: Install-Airc.ps1 must exit nonzero on failure under powershell.exe -File (PS 4.0).

Regression of FR #3685: on Windows PowerShell 4.0, an uncaught throw after
try/catch/finally leaves the -File process at exit 0, so Install-Airc.cmd logs
ok and msiexec reports success with no Airc service.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

INSTALL_PS1 = ROOT / "airc" / "scripts" / "Install-Airc.ps1"
INSTALL_CMD = ROOT / "airc" / "scripts" / "Install-Airc.cmd"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_fr3759_install_ps1_explicit_exit_not_bare_throw():
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "FR #3759" in text
    assert "$script:AircExitCode" in text
    assert "exit [int]$script:AircExitCode" in text
    # Outer catch must not end with a bare throw as the failure signal.
    # Allow inner Install-AircConsole catch to still throw into the outer catch.
    outer = text.rsplit("} catch {", 1)[-1]
    # After the last outer-catch body, we set AircExitCode = 1 (not throw-only).
    assert "$script:AircExitCode = 1" in outer
    assert "PS 4.0" in text or "powershell.exe -File" in text


def test_fr3759_install_cmd_fail_flag_belt_and_cleanup():
    text = INSTALL_CMD.read_text(encoding="utf-8")
    assert "FR #3759" in text or "FR3759" in text
    assert "FAILFLAG" in text
    assert 'if "%EC%"=="0" if exist "%FAILFLAG%"' in text
    # Stale flag must be deleted on the ok path too.
    assert 'if exist "%FAILFLAG%" del' in text or "del /f /q \"%FAILFLAG%\"" in text


def test_fr3759_troubleshooting_skill_row():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3759" in text or "3759" in text
    assert "exit" in text.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows powershell.exe -File")
def test_fr3759_powershell_file_exit1_after_catch_finally(tmp_path: Path):
    """Real powershell.exe -File: catch sets exit code, finally runs, process exits 1."""
    script = tmp_path / "fr3759-exit.ps1"
    script.write_text(
        textwrap.dedent(
            """
            $ErrorActionPreference = 'Stop'
            $script:AircExitCode = 0
            $script:SawFinally = $false
            try {
              throw 'FR3759 fixture failure'
            } catch {
              $script:AircExitCode = 1
            } finally {
              $script:SawFinally = $true
            }
            if (-not $script:SawFinally) { exit 99 }
            exit [int]$script:AircExitCode
            """
        ).strip()
        + "\n",
        encoding="ascii",
    )
    proc = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert proc.returncode == 1, (proc.stdout or "") + (proc.stderr or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd + powershell")
def test_fr3759_cmd_real_powershell_fixture_returns_nonzero_and_clears_flag(
    tmp_path: Path, monkeypatch
):
    """Install-Airc.cmd + real powershell -File fixture: FAIL exit=, no stale flag."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log_root = tmp_path / "ProgramData" / "Bobiverse" / "logs"
    log_root.mkdir(parents=True)

    # Production .cmd (Unblock uses real powershell; Install-Airc.ps1 is the fixture).
    raw = INSTALL_CMD.read_text(encoding="utf-8")
    (scripts / "Install-Airc.cmd").write_text(raw.replace("\n", "\r\n"), encoding="ascii")

    fixture = textwrap.dedent(
        """
        # FR #3759 fixture: mimic Install-Airc outer catch + fail flag + explicit exit.
        $ErrorActionPreference = 'Stop'
        $script:AircExitCode = 0
        $script:AircInstallOk = $false
        $logDir = Join-Path $env:ProgramData 'Bobiverse\\logs'
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        try {
          throw 'Ergo server PASS missing in release (FR3759 fixture)'
        } catch {
          $flag = Join-Path $logDir 'install-airc-fail-reported.flag'
          Set-Content -LiteralPath $flag -Value '1' -Encoding ASCII
          $script:AircExitCode = 1
        } finally {
          # no-op (Restore would run here in production)
        }
        exit [int]$script:AircExitCode
        """
    ).strip() + "\n"
    (scripts / "Install-Airc.ps1").write_text(fixture, encoding="ascii")

    # Outer reporter stub (should be skipped when flag exists).
    counter = tmp_path / "report-count.txt"
    (scripts / "Report-AircInstallCmdFailure.ps1").write_text(
        textwrap.dedent(
            f"""
            param([int]$ExitCode = 1, [string]$ScriptsDir = '', [string]$ArgsText = '')
            $c = '{counter}'
            $n = 0
            if (Test-Path -LiteralPath $c) {{ $n = [int](Get-Content -LiteralPath $c -Raw).Trim() }}
            $n++
            Set-Content -LiteralPath $c -Value $n -Encoding ASCII
            exit 0
            """
        ).strip()
        + "\n",
        encoding="ascii",
    )

    env = os.environ.copy()
    env["ProgramData"] = str(tmp_path / "ProgramData")
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
        timeout=90,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode != 0, out
    log = log_root / "install-airc.log"
    assert log.is_file(), out
    log_txt = log.read_text(encoding="utf-8", errors="replace")
    assert "FAIL exit=" in log_txt, log_txt
    flag = log_root / "install-airc-fail-reported.flag"
    assert not flag.exists(), "stale install-airc-fail-reported.flag must be cleared"
    # Flag was present so outer reporter should be skipped.
    if counter.exists():
        assert counter.read_text(encoding="ascii").strip() in ("", "0")


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd + powershell")
def test_fr3759_cmd_belt_when_ps_exits_0_but_flag_present(tmp_path: Path):
    """Belt: PS returns 0 but fail flag exists -> .cmd still FAIL and clears flag."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log_root = tmp_path / "ProgramData" / "Bobiverse" / "logs"
    log_root.mkdir(parents=True)

    raw = INSTALL_CMD.read_text(encoding="utf-8")
    (scripts / "Install-Airc.cmd").write_text(raw.replace("\n", "\r\n"), encoding="ascii")

    # Mimic broken PS 4.0: write flag then exit 0 (old throw path).
    (scripts / "Install-Airc.ps1").write_text(
        textwrap.dedent(
            """
            $logDir = Join-Path $env:ProgramData 'Bobiverse\\logs'
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
            Set-Content -LiteralPath (Join-Path $logDir 'install-airc-fail-reported.flag') -Value '1' -Encoding ASCII
            exit 0
            """
        ).strip()
        + "\n",
        encoding="ascii",
    )
    (scripts / "Report-AircInstallCmdFailure.ps1").write_text(
        "param([int]$ExitCode=1)\nexit 0\n", encoding="ascii"
    )

    env = os.environ.copy()
    env["ProgramData"] = str(tmp_path / "ProgramData")

    proc = subprocess.run(
        ["cmd.exe", "/d", "/c", "call", str(scripts / "Install-Airc.cmd")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(scripts),
        timeout=90,
    )
    assert proc.returncode != 0
    log_txt = (log_root / "install-airc.log").read_text(encoding="utf-8", errors="replace")
    assert "FR3759" in log_txt or "FAIL exit=" in log_txt
    assert not (log_root / "install-airc-fail-reported.flag").exists()
