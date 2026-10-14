"""FR #3887: stale install-airc-fail-reported.flag must not fail a good Install-Airc.cmd run.

A leftover flag from an earlier failed upgrade made a later successful Install-Airc.ps1
(EC=0, install-ok) look like FR #3759 PS 4.0 belt failure -> msiexec 1603 rollback.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

INSTALL_CMD = ROOT / "airc" / "scripts" / "Install-Airc.cmd"
SKILL = (
    ROOT
    / "airc"
    / ".grok"
    / "skills"
    / "bobiverse-airc-troubleshooting"
    / "SKILL.md"
)


def test_fr3887_cmd_clears_stale_flag_before_ps1():
    text = INSTALL_CMD.read_text(encoding="utf-8")
    assert "FR #3887" in text or "FR3887" in text
    assert "clearing stale fail-flag before install" in text
    # Clear must appear before the Install-Airc.ps1 -File invoke.
    clear_at = text.lower().find("fr3887 clearing stale")
    invoke_at = text.find('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%Install-Airc.ps1"')
    assert clear_at >= 0
    assert invoke_at >= 0
    assert clear_at < invoke_at
    # FR #3759 same-run belt must remain.
    assert 'if "%EC%"=="0" if exist "%FAILFLAG%"' in text


def test_fr3887_troubleshooting_skill_row():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #3887" in text or "3887" in text
    assert "stale" in text.lower()
    assert "fail-reported" in text or "fail-flag" in text.lower()


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd + powershell")
def test_fr3887_stale_flag_then_good_install_exits_0(tmp_path: Path):
    """Pre-seed stale flag; successful ps1 (exit 0, no new flag) -> cmd exit 0."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log_root = tmp_path / "ProgramData" / "Bobiverse" / "logs"
    log_root.mkdir(parents=True)

    # Stale flag from a prior failed run (the bug trigger).
    stale = log_root / "install-airc-fail-reported.flag"
    stale.write_text("stale-from-prior-run\n", encoding="ascii")

    raw = INSTALL_CMD.read_text(encoding="utf-8")
    (scripts / "Install-Airc.cmd").write_text(raw.replace("\n", "\r\n"), encoding="ascii")

    # Successful install fixture: exit 0, do not write a new fail flag.
    (scripts / "Install-Airc.ps1").write_text(
        textwrap.dedent(
            """
            $logDir = Join-Path $env:ProgramData 'Bobiverse\\logs'
            New-Item -ItemType Directory -Force -Path $logDir | Out-Null
            $log = Join-Path $logDir 'install-airc.log'
            Add-Content -LiteralPath $log -Value 'fixture install-ok' -Encoding ascii
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
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, out
    log_txt = (log_root / "install-airc.log").read_text(encoding="utf-8", errors="replace")
    assert "FR3887 clearing stale fail-flag" in log_txt, log_txt
    assert "Install-Airc.cmd ok" in log_txt, log_txt
    assert "treating as FAIL" not in log_txt, log_txt
    assert not stale.exists(), "ok path must leave no fail flag"


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd + powershell")
def test_fr3887_same_run_fail_flag_still_trips_fr3759_belt(tmp_path: Path):
    """FR #3759 belt preserved: ps1 writes flag then exits 0 -> cmd still FAIL."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log_root = tmp_path / "ProgramData" / "Bobiverse" / "logs"
    log_root.mkdir(parents=True)

    raw = INSTALL_CMD.read_text(encoding="utf-8")
    (scripts / "Install-Airc.cmd").write_text(raw.replace("\n", "\r\n"), encoding="ascii")

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
