"""FR #8493: a low-free job-worktree base moves to the data drive."""
from __future__ import annotations

import textwrap

from test_fr4988_job_worktree_base import COMMON, _ps


def test_fr8493_low_free_bridge_redirects_to_data_drive(tmp_path):
    bridge = tmp_path / "bridge-home"
    bridge.mkdir()
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $disks = @(
            [pscustomobject]@{{ Root = 'C:\\'; DriveType = 3 }},
            [pscustomobject]@{{ Root = 'D:\\'; DriveType = 3 }}
        )
        $b = Get-BobiverseJobWorktreeBase -BridgeHome '{bridge.as_posix()}' -Disks $disks -SystemDrive 'C:' -AssumeFreeGB 0.4
        Write-Output ("BASE=" + $b)
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\")
    assert "BASE=D:\\ai\\worktrees" in out


def test_fr8493_roomy_override_stays(tmp_path):
    base = tmp_path / "wtbase"
    base.mkdir()
    script = textwrap.dedent(
        f"""
        . '{COMMON.as_posix()}'
        $disks = @(
            [pscustomobject]@{{ Root = 'C:\\'; DriveType = 3 }},
            [pscustomobject]@{{ Root = 'D:\\'; DriveType = 3 }}
        )
        $b = Get-BobiverseJobWorktreeBase -Override '{base.as_posix()}' -Disks $disks -SystemDrive 'C:' -AssumeFreeGB 40
        Write-Output ("BASE=" + $b)
        """
    )
    r = _ps(script)
    assert r.returncode == 0, r.stdout + r.stderr
    out = (r.stdout + r.stderr).replace("/", "\\")
    expect = str(base).replace("/", "\\")
    assert f"BASE={expect}" in out
