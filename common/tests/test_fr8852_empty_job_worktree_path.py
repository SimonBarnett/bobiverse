"""FR #8852: refuse empty/relative/install-relative job worktree paths before git worktree add."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
GUARD = ROOT / "common" / "scripts" / "bob_install_root_guard.py"
AGENTS = ROOT / "bob" / "agents" / "worker" / "AGENTS.md"
FR_SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md"
SEAT_SKILL = ROOT / "bob" / "agents" / "worker" / ".grok" / "skills" / "bobiverse-worker-seat" / "SKILL.md"


def _ps(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(ROOT),
    )


def test_fr8852_assert_helper_exists_in_common():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "function Assert-BobiverseJobWorktreePath" in text
    assert "FR #8852" in text
    assert "common\\scripts\\Bobiverse-Common.ps1" in text or "common/scripts/Bobiverse-Common.ps1" in text


def test_fr8852_refuse_empty_relative_and_under_install(tmp_path: Path):
    install = tmp_path / "bob"
    install.mkdir()
    good = tmp_path / "worktrees" / "bobiverse" / "fr-8852"
    good.mkdir(parents=True)
    under = install / "origin" / "main"
    under.mkdir(parents=True)
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $install = '{install.as_posix()}'
        $good = '{good.as_posix()}'
        $under = '{under.as_posix()}'
        try {{
            Assert-BobiverseJobWorktreePath -Path '' | Out-Null
            Write-Output 'EMPTY_OK'
        }} catch {{
            Write-Output ('EMPTY_REFUSED=' + $_.Exception.Message)
        }}
        try {{
            Assert-BobiverseJobWorktreePath -Path $null | Out-Null
            Write-Output 'NULL_OK'
        }} catch {{
            Write-Output ('NULL_REFUSED=' + $_.Exception.Message)
        }}
        try {{
            Assert-BobiverseJobWorktreePath -Path 'origin/main' | Out-Null
            Write-Output 'REL_OK'
        }} catch {{
            Write-Output ('REL_REFUSED=' + $_.Exception.Message)
        }}
        try {{
            Assert-BobiverseJobWorktreePath -Path $under -InstallRoot $install | Out-Null
            Write-Output 'UNDER_OK'
        }} catch {{
            Write-Output ('UNDER_REFUSED=' + $_.Exception.Message)
        }}
        try {{
            $p = Assert-BobiverseJobWorktreePath -Path $good -InstallRoot $install
            Write-Output ('GOOD=' + $p)
        }} catch {{
            Write-Output ('GOOD_FAIL=' + $_.Exception.Message)
        }}
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert "EMPTY_REFUSED=" in out and "FR #8852" in out
    assert "NULL_REFUSED=" in out
    assert "REL_REFUSED=" in out
    assert "UNDER_REFUSED=" in out
    assert "EMPTY_OK" not in out
    assert "REL_OK" not in out
    assert "UNDER_OK" not in out
    assert "GOOD=" in out
    assert "GOOD_FAIL=" not in out


def test_fr8852_python_refuse_empty_job_worktree_path(tmp_path: Path):
    import sys

    sys.path.insert(0, str(ROOT / "common" / "scripts"))
    import bob_install_root_guard as guard

    install = tmp_path / "bob"
    install.mkdir()
    good = tmp_path / "wt" / "fr-8852"
    good.mkdir(parents=True)
    under = install / "origin" / "main"
    under.mkdir(parents=True)

    assert guard.refuse_empty_job_worktree_path("") is not None
    assert guard.refuse_empty_job_worktree_path(None) is not None
    assert guard.refuse_empty_job_worktree_path("   ") is not None
    assert "FR #8852" in guard.refuse_empty_job_worktree_path("origin/main")
    assert guard.refuse_empty_job_worktree_path(under, install_root=install) is not None
    assert guard.refuse_empty_job_worktree_path(good, install_root=install) is None


def test_fr8852_docs_pin_common_scripts_path_and_assert():
    agents = AGENTS.read_text(encoding="utf-8")
    assert "FR #8852" in agents
    assert "Assert-BobiverseJobWorktreePath" in agents or "common\\scripts\\Bobiverse-Common.ps1" in agents
    skill = FR_SKILL.read_text(encoding="utf-8")
    assert "FR #8852" in skill
    assert "Assert-BobiverseJobWorktreePath" in skill
    assert "common\\scripts\\Bobiverse-Common.ps1" in skill or "common/scripts/Bobiverse-Common.ps1" in skill
    seat = SEAT_SKILL.read_text(encoding="utf-8")
    assert "Assert-BobiverseJobWorktreePath -Path $wt" in seat
    assert "resolve `$wt` via" in seat
