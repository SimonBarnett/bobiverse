"""FR #3554: MSI install log must not Full-Recurse Protect ProgramData on every line."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"


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


def test_fr3554_ensure_has_protect_mode_and_cache():
    t = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #3554" in t
    assert "ProtectMode" in t
    assert "LogsOnly" in t
    assert "BobiverseProgramDataProtectCache" in t
    assert "BOBIVERSE_PROGRAMDATA_ROOT" in t
    assert "-ProtectMode" in t
    assert "Get-BobiverseMsiLogDir" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3554_n_log_writes_protect_at_most_once(tmp_path: Path):
    pd = tmp_path / "ProgramDataBobiverse"
    # Fake a fat tree that Full -Recurse would pay for (must not be touched repeatedly).
    fat = pd / "update" / "airc" / "pad"
    fat.mkdir(parents=True)
    for i in range(40):
        (fat / f"blob-{i}.bin").write_bytes(b"x" * 1024)

    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:BobiverseProgramDataProtectCache = @{{}}
        $env:BOBIVERSE_PROGRAMDATA_ROOT = '{pd}'
        # Log writes under env root use ProtectMode None (writable for unelevated pytest).
        1..5 | ForEach-Object {{
          Write-BobiverseMsiInstallLog -Product airc -Message ("fr3554-line-" + $_)
        }}
        $logPath = Join-Path '{pd}' 'logs\\install-airc.log'
        $joined = @(Get-Content -LiteralPath $logPath -ErrorAction Stop).Count
        if ($joined -lt 5) {{ throw ("expected >=5 log lines got " + $joined) }}
        # Explicit LogsOnly: first Protect, second must be cached (FR #3554).
        $null = Ensure-BobiverseProgramDataRoot -Root '{pd}' -ProtectMode LogsOnly *>&1
        $msg = Ensure-BobiverseProgramDataRoot -Root '{pd}' -ProtectMode LogsOnly *>&1 | Out-String
        if ($msg -notmatch 'FR #3554' -or $msg -notmatch 'cached|skipped') {{
          throw ("expected cached skip, got: " + $msg)
        }}
        if ($msg -match 're-locking pre-existing') {{
          throw 'cached path must not re-lock'
        }}
        Write-Output 'protect-once-ok'
        """
    )
    proc = _ps(script, env={"BOBIVERSE_PROGRAMDATA_ROOT": str(pd)}, timeout=45)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "protect-once-ok" in text
    log = pd / "logs" / "install-airc.log"
    assert log.is_file()
    assert log.read_text(encoding="utf-8").count("fr3554-line-") >= 5


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_fr3554_env_root_redirects_away_from_live_programdata(tmp_path: Path):
    pd = tmp_path / "pd-redirect"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $script:BobiverseProgramDataProtectCache = @{{}}
        $env:BOBIVERSE_PROGRAMDATA_ROOT = '{pd}'
        $dir = Get-BobiverseMsiLogDir
        if ($dir -notlike '{pd}*') {{ throw ("log dir not under tmp: " + $dir) }}
        if ($dir -match '(?i)C:\\\\ProgramData\\\\Bobiverse') {{ throw 'must not use live ProgramData' }}
        Write-Output 'redirect-ok'
        """
    )
    proc = _ps(script, env={"BOBIVERSE_PROGRAMDATA_ROOT": str(pd)}, timeout=30)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    assert proc.returncode == 0, text
    assert "redirect-ok" in text


def test_fr3554_skill_mentions_log_protect_once():
    skill = SKILL.read_text(encoding="utf-8")
    assert "FR #3554" in skill
    assert "LogsOnly" in skill or "BOBIVERSE_PROGRAMDATA_ROOT" in skill
