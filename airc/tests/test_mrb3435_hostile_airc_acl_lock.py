"""MRB #3435 hostile pins for FR #3394 ACL fail-closed + purge allow-list."""
from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common/scripts/Bobiverse-Common.ps1"
INSTALL = ROOT / "airc/scripts/Install-Airc.ps1"
UNINSTALL = ROOT / "airc/scripts/Uninstall-Airc.ps1"
SKILL = ROOT / "airc/.grok/skills/bobiverse-airc/SKILL.md"
POST = ROOT / "common/docs/post-install.md"


def _ps(script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
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


def test_mrb3435_install_forces_nostart_then_protect_then_start():
    t = INSTALL.read_text(encoding="utf-8")
    # Unconditional delay of Start-Service (not only when -NoStart was passed in).
    assert re.search(r"\$args\.NoStart\s*=\s*\$true", t)
    idx_legacy = t.find("& $installLegacy")
    idx_final_protect = t.rfind("Protect-BobiverseInstallTree")
    idx_start = t.find("Start-Service -Name 'Airc'")
    assert idx_legacy > 0
    assert idx_final_protect > idx_legacy
    assert idx_start > idx_final_protect
    # FR #3652: install-begin (Write-BobiverseMsiInstallLog) before ProgramData Ensure
    # so CA logs show progress; Ensure itself must be LogsOnly (not Full -Recurse).
    assert t.find("install-begin") < t.find("Ensure-BobiverseProgramDataRoot -FailClosed -ProtectMode LogsOnly")
    assert "Ensure-BobiverseProgramDataRoot -FailClosed -ProtectMode LogsOnly" in t


def test_mrb3435_skill_post_contiguous_failclosed():
    skill = SKILL.read_text(encoding="utf-8")
    post = POST.read_text(encoding="utf-8")
    assert "FR #3394" in skill or "#3394" in skill
    assert "FailClosed" in skill or "fail-closed" in skill.lower()
    assert "Ensure-BobiverseProgramDataRoot" in skill or "ProgramData" in skill
    assert "FR #3394" in post or "#3394" in post


def test_mrb3435_uninstall_warns_on_refused_path():
    t = UNINSTALL.read_text(encoding="utf-8")
    assert "refuse purge path outside allow-list" in t
    assert "Test-BobiverseAircPurgePathAllowed" in t


@pytest.mark.skipif(os.name != "nt", reason="Windows path only")
def test_mrb3435_protect_failclosed_throws_when_missing(tmp_path: Path):
    missing = tmp_path / "no-such-airc-tree"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        try {{
            Protect-BobiverseInstallTree -Path '{missing}' -Recurse -FailClosed
            throw 'expected FailClosed throw'
        }} catch {{
            if ($_.Exception.Message -notmatch 'FailClosed|missing') {{ throw }}
            Write-Output 'missing-throw-ok'
        }}
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "missing-throw-ok" in (proc.stdout or "")


@pytest.mark.skipif(os.name != "nt", reason="Windows path only")
def test_mrb3435_purge_allowlist_rejects_traversal(tmp_path: Path):
    install = tmp_path / "ai" / "airc"
    home = tmp_path / "home"
    pd = tmp_path / "ProgramData" / "Bobiverse"
    install.mkdir(parents=True)
    home.mkdir()
    pd.mkdir(parents=True)
    # Normalized traversal must not escape install_root into Temp.
    evil = install / ".." / ".." / "Windows" / "Temp" / "canary-mrb3435"
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON}'
        $bad = Test-BobiverseAircPurgePathAllowed -Path '{evil}' -InstallRoot '{install}' -ConsoleHome '{home}' -ProgramDataRoot '{pd}'
        if ($bad) {{ throw 'traversal canary must be refused' }}
        $ok = Test-BobiverseAircPurgePathAllowed -Path '{install}' -InstallRoot '{install}' -ConsoleHome '{home}' -ProgramDataRoot '{pd}'
        if (-not $ok) {{ throw 'install root must be allowed' }}
        Write-Output 'traversal-ok'
        """
    )
    proc = _ps(script)
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    assert "traversal-ok" in (proc.stdout or "")


def test_mrb3435_msi_log_dir_prefers_ensure():
    t = COMMON.read_text(encoding="utf-8-sig")
    idx_fn = t.find("function Get-BobiverseMsiLogDir")
    assert idx_fn > 0
    chunk = t[idx_fn : idx_fn + 900]
    assert "Ensure-BobiverseProgramDataRoot" in chunk
