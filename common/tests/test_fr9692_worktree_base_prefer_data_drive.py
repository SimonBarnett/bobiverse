"""FR #9692: prefer data-drive job worktrees over system-drive BOB_BRIDGE_HOME\\worktrees."""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"
CLEAR = ROOT / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"


def _ps(script: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
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


def test_fr9692_bridge_on_system_drive_prefers_data_drive(tmp_path: Path):
    c = tmp_path / "C"
    d = tmp_path / "D"
    bridge = c / "Users" / "simon" / ".grok" / "bob-bridge"
    bridge.mkdir(parents=True)
    c.mkdir(exist_ok=True)
    d.mkdir(exist_ok=True)
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
        $b = Get-BobiverseJobWorktreeBase -BridgeHome '{bridge.as_posix()}' -Disks $disks -SystemDrive '{c_root.rstrip(chr(92))}' -AssumeFreeGB 50
        Write-Output ("BASE=" + $b)
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\")
    assert expect.lower() in out.lower()
    assert "bob-bridge" not in out.lower()


def test_fr9692_explicit_job_base_on_system_drive_kept(tmp_path: Path):
    c = tmp_path / "C"
    d = tmp_path / "D"
    base = c / "Users" / "simon" / ".grok" / "bob-bridge" / "worktrees"
    base.mkdir(parents=True)
    c.mkdir(exist_ok=True)
    d.mkdir(exist_ok=True)
    c_root = str(c).replace("/", "\\").rstrip("\\") + "\\"
    d_root = str(d).replace("/", "\\").rstrip("\\") + "\\"
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $disks = @(
            [pscustomobject]@{{ Root = '{c_root}'; DriveType = 3 }},
            [pscustomobject]@{{ Root = '{d_root}'; DriveType = 3 }}
        )
        $env:BOB_JOB_WORKTREE_BASE = '{base.as_posix()}'
        $b = Get-BobiverseJobWorktreeBase -Disks $disks -SystemDrive '{c_root.rstrip(chr(92))}' -AssumeFreeGB 50
        Write-Output ("BASE=" + $b)
        """
    )
    r = _ps(script, env={"BOB_JOB_WORKTREE_BASE": str(base)})
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\").lower()
    assert "bob-bridge" in out and "worktrees" in out


def test_fr9692_clear_reclaims_unlist_orphan_with_git_marker():
    text = CLEAR.read_text(encoding="utf-8-sig")
    assert "FR #9692" in text
    assert "unlist" in text.lower() or "not in git worktree list" in text.lower() or "not listed" in text.lower()
    assert "BOB_BRIDGE_HOME" in text
    assert "safe.directory" in text or "dubious ownership" in text.lower()
