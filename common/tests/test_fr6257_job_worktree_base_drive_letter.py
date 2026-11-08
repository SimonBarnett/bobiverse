"""FR #6257: Get-BobiverseJobWorktreeBase must not resolve under worker CWD.

Windows Path.Combine treats 'C:' (drive letter after TrimEnd of 'C:\\') as
cwd-relative on that drive. Default base must be <drive>\\ai\\worktrees.
"""
from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

from repo_layout import ROOT

COMMON = ROOT / "common" / "scripts" / "Bobiverse-Common.ps1"


def _ps(script: str, *, cwd: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    for k in ("BOB_JOB_WORKTREE_BASE", "BOB_BRIDGE_HOME"):
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
        cwd=cwd,
        env=full_env,
    )


def test_fr6257_system_drive_default_not_under_worker_cwd(tmp_path: Path):
    """Literal C:\\ data root from a worker-like CWD must yield C:\\ai\\worktrees.

    Reproduces the Win32 quirk: TrimEnd('\\\\') on 'C:\\\\' yields 'C:', and
    Path.Combine('C:', 'ai', 'worktrees') is cwd-relative on that drive.
    """
    worker = tmp_path / "bob" / "worker"
    worker.mkdir(parents=True)
    expect = r"C:\ai\worktrees"
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $disks = @(
            [pscustomobject]@{{ Root = 'C:\\'; DriveType = 3 }}
        )
        $b = Get-BobiverseJobWorktreeBase -Disks $disks -SystemDrive 'C:'
        Write-Output ("BASE=" + $b)
        $p = Get-BobiverseJobWorktreePath -Repo 'SimonBarnett/bobiverse' -Job 'fr-6257' -Base $b
        Write-Output ("PATH=" + $p)
        """
    )
    r = _ps(script, cwd=str(worker))
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\")
    base_line = [ln for ln in out.splitlines() if ln.startswith("BASE=")]
    assert base_line, out
    got = base_line[0][5:].strip()
    assert got.lower() == expect.lower(), f"got={got!r} expect={expect!r} out={out}"
    assert "\\bob\\worker\\" not in got.lower()
    assert got.lower().endswith("\\ai\\worktrees")
    assert "fr-6257" in out


def test_fr6257_literal_c_colon_combine_guard_in_source():
    """Source must keep a trailing slash on drive-only roots before Path.Combine."""
    text = COMMON.read_text(encoding="utf-8-sig")
    assert "FR #6257" in text
    # Drive-only re-root (C: -> C:\\) before Combine for default ai\\worktrees.
    assert "^[A-Za-z]:$" in text
