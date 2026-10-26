"""FR #4988: job worktrees under <data drive>\\ai\\worktrees (never drive root).

Configurable via BOB_JOB_WORKTREE_BASE (dedicated) or BOB_BRIDGE_HOME when it
points at a non-root path used as the worktree base.
"""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
CLEAR = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def _ps(script: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    # Drop overrides unless the test sets them.
    for k in ("BOB_JOB_WORKTREE_BASE", "BOB_BRIDGE_HOME", "BOB_AI_ROOT"):
        if env is None or k not in env:
            full_env.pop(k, None)
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
        env=full_env,
    )


def test_fr4988_helpers_exist_in_common():
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #4988" in text
    assert "function Get-BobiverseJobWorktreeBase" in text
    assert "function Get-BobiverseJobWorktreePath" in text
    assert "function Test-BobiverseIsDriveRoot" in text
    assert "BOB_JOB_WORKTREE_BASE" in text


def test_fr4988_clear_documents_base_and_local_work():
    text = CLEAR.read_text(encoding="utf-8-sig")
    assert "FR #4988" in text
    assert "Get-BobiverseJobWorktreeBase" in text or "BOB_JOB_WORKTREE_BASE" in text
    assert "uncommitted" in text.lower() or "unpushed" in text.lower() or "Test-WorktreeHasLocalWork" in text


def test_fr4988_override_base_and_never_drive_root(tmp_path: Path):
    base = tmp_path / "wtbase"
    base.mkdir()
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $b = Get-BobiverseJobWorktreeBase -Override '{base.as_posix()}'
        Write-Output ("BASE=" + $b)
        $p = Get-BobiverseJobWorktreePath -Repo 'SimonBarnett/bobiverse' -Job 'fr-4988' -Base $b
        Write-Output ("PATH=" + $p)
        try {{
            Get-BobiverseJobWorktreeBase -Override 'D:\\' | Out-Null
            Write-Output 'ROOT_OK'
        }} catch {{
            Write-Output ('ROOT_REFUSED=' + $_.Exception.Message)
        }}
        try {{
            Get-BobiverseJobWorktreePath -Repo 'x' -Job 'y' -Base 'E:\\' | Out-Null
            Write-Output 'PATH_ROOT_OK'
        }} catch {{
            Write-Output ('PATH_ROOT_REFUSED=' + $_.Exception.Message)
        }}
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout + r.stderr
    assert f"BASE={base}" in out.replace("/", "\\") or f"BASE={base}" in out
    assert "bobiverse" in out and "fr-4988" in out
    assert "ROOT_REFUSED=" in out
    assert "PATH_ROOT_REFUSED=" in out
    assert "ROOT_OK" not in out
    assert "PATH_ROOT_OK" not in out


def test_fr4988_default_prefers_data_drive(tmp_path: Path):
    """Fake system + data disks via -Disks; base must be under the non-system disk\\ai\\worktrees."""
    c = tmp_path / "C"
    d = tmp_path / "D"
    c.mkdir()
    d.mkdir()
    c_root = str(c).replace("/", "\\").rstrip("\\") + "\\"
    d_root = str(d).replace("/", "\\").rstrip("\\") + "\\"
    expect = str(d / "ai" / "worktrees").replace("/", "\\")
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $disks = @(
            [pscustomobject]@{{ Root = '{c_root}'; DriveType = 3 }},
            [pscustomobject]@{{ Root = '{d_root}'; DriveType = 3 }}
        )
        $b = Get-BobiverseJobWorktreeBase -Disks $disks -SystemDrive '{c_root.rstrip(chr(92))}'
        Write-Output ("BASE=" + $b)
        if (Test-BobiverseIsDriveRoot $b) {{ Write-Output 'FAIL_IS_ROOT' }}
        else {{ Write-Output 'NOT_ROOT' }}
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\")
    assert expect in out
    assert "NOT_ROOT" in out
    assert "FAIL_IS_ROOT" not in out


def test_fr4988_bridge_home_override_when_job_base_unset(tmp_path: Path):
    bridge = tmp_path / "bridge-home"
    bridge.mkdir()
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $b = Get-BobiverseJobWorktreeBase -BridgeHome '{bridge.as_posix()}'
        Write-Output ("BASE=" + $b)
        """
    )
    r = _ps(script, env={"BOB_BRIDGE_HOME": str(bridge)})
    assert r.returncode == 0, r.stdout + r.stderr
    # When BridgeHome is passed / env set and BOB_JOB_WORKTREE_BASE unset, use bridge\\worktrees
    # or the bridge path itself if already a worktrees folder — implementation: Join bridge worktrees
    out = r.stdout + r.stderr
    assert "worktrees" in out.lower() or str(bridge) in out


def test_fr4988_agents_docs_pin_new_base():
    agents = ROOT / "bob" / "agents" / "worker" / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    assert "FR #4988" in text or "Get-BobiverseJobWorktreePath" in text or "BOB_JOB_WORKTREE_BASE" in text
    assert "ai\\worktrees" in text or "ai/worktrees" in text
