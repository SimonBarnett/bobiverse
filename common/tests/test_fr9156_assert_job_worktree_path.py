# -*- coding: utf-8 -*-
"""FR #9156 / #8852: Assert-BobiverseJobWorktreePath + refuse_empty_job_worktree_path."""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
GUARD = ROOT / "common" / "scripts" / "bob_install_root_guard.py"


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
        env={k: v for k, v in os.environ.items() if k not in ("BOB_JOB_WORKTREE_BASE",)},
    )


def test_fr9156_assert_function_exists_in_common():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "function Assert-BobiverseJobWorktreePath" in text
    assert "FR #8852" in text or "FR #9156" in text


def test_fr9156_refuse_empty_helper_in_python_guard():
    text = GUARD.read_text(encoding="utf-8")
    assert "def refuse_empty_job_worktree_path" in text
    sys.path.insert(0, str(GUARD.parent))
    import bob_install_root_guard as guard  # noqa: WPS433

    assert guard.refuse_empty_job_worktree_path("") is not None
    assert guard.refuse_empty_job_worktree_path("   ") is not None
    assert guard.refuse_empty_job_worktree_path("origin/main") is not None
    assert guard.refuse_empty_job_worktree_path("origin\\main") is not None
    assert guard.refuse_empty_job_worktree_path("rel/path") is not None
    ok = guard.refuse_empty_job_worktree_path(
        r"D:\ai\worktrees\bobiverse\fr-9156",
        install_root=r"C:\ai\bob",
    )
    assert ok is None
    under = guard.refuse_empty_job_worktree_path(
        r"C:\ai\bob\origin\main",
        install_root=r"C:\ai\bob",
    )
    assert under is not None
    assert "8852" in under or "under install" in under.lower()


def test_fr9156_assert_refuses_empty_relative_origin_main_under_install(tmp_path: Path):
    install = tmp_path / "install"
    install.mkdir()
    good = tmp_path / "worktrees" / "bobiverse" / "fr-9156"
    good.mkdir(parents=True)
    inst = str(install).replace("'", "''")
    good_s = str(good).replace("'", "''")
    script = textwrap.dedent(
        f"""
        $ErrorActionPreference = 'Stop'
        . '{COMMON.as_posix()}'
        $install = '{inst}'
        function _try([string]$label, [scriptblock]$b) {{
          try {{ & $b | Out-Null; Write-Output ($label + '=OK') }}
          catch {{ Write-Output ($label + '=REFUSED:' + $_.Exception.Message) }}
        }}
        _try 'EMPTY' {{ Assert-BobiverseJobWorktreePath -Path '' -InstallRoot $install }}
        _try 'WS' {{ Assert-BobiverseJobWorktreePath -Path '   ' -InstallRoot $install }}
        _try 'REL' {{ Assert-BobiverseJobWorktreePath -Path 'origin/main' -InstallRoot $install }}
        _try 'UNDER' {{ Assert-BobiverseJobWorktreePath -Path (Join-Path $install 'origin\\main') -InstallRoot $install }}
        _try 'GOOD' {{ Assert-BobiverseJobWorktreePath -Path '{good_s}' -InstallRoot $install }}
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert "EMPTY=REFUSED:" in out
    assert "WS=REFUSED:" in out
    assert "REL=REFUSED:" in out
    assert "UNDER=REFUSED:" in out
    assert "GOOD=OK" in out
    assert "GOOD=REFUSED:" not in out
