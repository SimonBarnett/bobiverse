"""FR #8023: fail-closed prune of closed/merged job worktrees.

Dirty, unpushed, and unknown trees survive. Clean closed-job trees prune.
Failed fetch under -PruneClosedJobs removes nothing. SeatDisk skips TEMP+.git.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
SEAT_DISK = REPO / "common" / "scripts" / "Clear-BobiverseSeatDisk.ps1"

WIN = pytest.mark.skipif(
    sys.platform != "win32" or not shutil.which("powershell"),
    reason="needs Windows PowerShell",
)


def _run_ps(
    script: Path,
    *extra: str,
    env: dict | None = None,
    worktree_base: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *extra,
    ]
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    # Avoid scanning the live seat worktree base during fixtures.
    if worktree_base is not None:
        run_env["BOB_JOB_WORKTREE_BASE"] = str(worktree_base)
    elif "BOB_JOB_WORKTREE_BASE" not in run_env:
        run_env["BOB_JOB_WORKTREE_BASE"] = str(Path(os.environ.get("TEMP", ".") ) / "bobiverse-fr8023-empty-base")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=run_env)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _init_bare_and_clone(tmp: Path) -> tuple[Path, Path]:
    bare = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    clone = tmp / "clone"
    subprocess.run(["git", "clone", str(bare), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.email", "t@example.com")
    _git(clone, "config", "user.name", "t")
    (clone / "README").write_text("init\n", encoding="utf-8")
    _git(clone, "add", "README")
    _git(clone, "commit", "-m", "init")
    _git(clone, "push", "-u", "origin", "main")
    return bare, clone


def _add_wt(clone: Path, path: Path, branch: str, start: str = "origin/main") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", "-b", branch, str(path), start],
        check=True,
        capture_output=True,
    )


def _push_branch(wt: Path, branch: str) -> str:
    _git(wt, "push", "-u", "origin", branch)
    head = subprocess.run(
        ["git", "-C", str(wt), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return head


def _seat_marker(wt: Path, issue: int) -> None:
    # Stale marker (pid dead, old mtime) so Clear does not treat as active seat.
    marker = {
        "nick": "test-seat",
        "pid": 1,
        "issue": issue,
        "repo": "SimonBarnett/bobiverse",
    }
    path = wt / ".bobiverse-seat"
    path.write_text(json.dumps(marker), encoding="utf-8")
    old = 100 * 3600
    os.utime(path, (os.path.getmtime(path) - old, os.path.getmtime(path) - old))


def _write_gh_stub(bin_dir: Path, mapping: dict[str, object]) -> Path:
    """Write gh.cmd stub that returns fixture JSON; no secrets."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    map_path = bin_dir / "gh_map.json"
    map_path.write_text(json.dumps(mapping), encoding="utf-8")
    # PowerShell helper invoked by gh.cmd
    helper = bin_dir / "gh_stub.ps1"
    helper.write_text(
        textwrap.dedent(
            f"""
            $ErrorActionPreference = 'Stop'
            $map = Get-Content -LiteralPath '{map_path}' -Raw | ConvertFrom-Json
            function Get-Entry([string]$Key) {{
              $prop = $map.PSObject.Properties[$Key]
              if (-not $prop) {{ return $null }}
              return $prop.Value
            }}
            $joined = ($args -join ' ')
            if ($joined -match 'issue view\\s+(\\d+)') {{
              $entry = Get-Entry ("issue:" + $Matches[1])
              if (-not $entry) {{ exit 1 }}
              if ($entry.PSObject.Properties['exit'] -and $entry.exit) {{ exit [int]$entry.exit }}
              Write-Output ([string]$entry.json)
              exit 0
            }}
            if ($joined -match 'pr view\\s+(\\d+)') {{
              $entry = Get-Entry ("pr:" + $Matches[1])
              if (-not $entry) {{ exit 1 }}
              if ($entry.PSObject.Properties['exit'] -and $entry.exit) {{ exit [int]$entry.exit }}
              Write-Output ([string]$entry.json)
              exit 0
            }}
            if ($joined -match 'pr list') {{
              $entry = Get-Entry 'prlist'
              if ($entry) {{
                if ($entry.PSObject.Properties['exit'] -and $entry.exit) {{ exit [int]$entry.exit }}
                Write-Output ([string]$entry.json)
                exit 0
              }}
              Write-Output '[]'
              exit 0
            }}
            exit 1
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    gh_cmd = bin_dir / "gh.cmd"
    gh_cmd.write_text(
        f'@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "{helper}" %*\r\n',
        encoding="utf-8",
    )
    return bin_dir


def test_fr8023_script_has_fail_closed_markers():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "FR #8023" in text
    assert "Get-WorktreeLocalWorkState" in text
    assert "PruneClosedJobs" in text
    assert "kept-remove-failed" in text
    assert "worktree remove --force" not in text or "without --force" in text.lower()
    # remove without --force is the live path
    assert "worktree remove $p" in text or "worktree remove $p " in text.replace("\r", "")


@WIN
def test_fr8023_prune_keeps_dirty_unpushed_unknown_and_prunes_closed(tmp_path: Path, monkeypatch):
    bare, clone = _init_bare_and_clone(tmp_path / "repo")
    base = tmp_path / "worktrees" / "bobiverse"
    base.mkdir(parents=True)

    dirty = base / "fr-7999"
    untracked = base / "fr-8001"
    unpushed_no_up = base / "fr-8002"
    unpushed_up = base / "fr-8003"
    corrupt = base / "fr-8004"
    open_job = base / "fr-8005"
    closed_job = base / "fr-8023"
    merged_head = base / "fr-8006"

    _add_wt(clone, dirty, "fr-7999")
    _seat_marker(dirty, 7999)
    (dirty / "WIP.txt").write_text("dirty\n", encoding="utf-8")
    (dirty / "README").write_text("changed\n", encoding="utf-8")

    _add_wt(clone, untracked, "fr-8001")
    _seat_marker(untracked, 8001)
    (untracked / "only-new.txt").write_text("u\n", encoding="utf-8")

    _add_wt(clone, unpushed_no_up, "fr-8002")
    _seat_marker(unpushed_no_up, 8002)
    (unpushed_no_up / "c.txt").write_text("c\n", encoding="utf-8")
    _git(unpushed_no_up, "add", "c.txt")
    _git(unpushed_no_up, "commit", "-m", "local-only")
    # detach upstream if any
    subprocess.run(
        ["git", "-C", str(unpushed_no_up), "branch", "--unset-upstream"],
        capture_output=True,
    )

    _add_wt(clone, unpushed_up, "fr-8003")
    _seat_marker(unpushed_up, 8003)
    _push_branch(unpushed_up, "fr-8003")
    (unpushed_up / "ahead.txt").write_text("a\n", encoding="utf-8")
    _git(unpushed_up, "add", "ahead.txt")
    _git(unpushed_up, "commit", "-m", "ahead")

    _add_wt(clone, corrupt, "fr-8004")
    _seat_marker(corrupt, 8004)
    _push_branch(corrupt, "fr-8004")
    git_marker = corrupt / ".git"
    if git_marker.is_dir():
        shutil.rmtree(git_marker)
    elif git_marker.exists():
        git_marker.unlink()
    git_marker.write_text("gitdir: /nonexistent/path\n", encoding="utf-8")

    _add_wt(clone, open_job, "fr-8005")
    _seat_marker(open_job, 8005)
    _push_branch(open_job, "fr-8005")

    _add_wt(clone, closed_job, "fr-8023")
    _seat_marker(closed_job, 8023)
    closed_oid = _push_branch(closed_job, "fr-8023")

    _add_wt(clone, merged_head, "fr-8006")
    _seat_marker(merged_head, 8006)
    merged_oid = _push_branch(merged_head, "fr-8006")
    # Delete remote branch but keep local HEAD == merged oid proof.
    subprocess.run(
        ["git", "-C", str(clone), "push", "origin", "--delete", "fr-8006"],
        capture_output=True,
    )

    gh_bin = _write_gh_stub(
        tmp_path / "ghbin",
        {
            "issue:7999": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8001": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8002": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8003": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8004": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8005": {"json": json.dumps({"state": "OPEN"})},
            "issue:8023": {"json": json.dumps({"state": "CLOSED"})},
            "issue:8006": {"json": json.dumps({"state": "CLOSED"})},
            "prlist": {"json": json.dumps([{"headRefOid": merged_oid}])},
        },
    )

    env = os.environ.copy()
    env["PATH"] = str(gh_bin) + os.pathsep + env.get("PATH", "")
    env["BOB_JOB_WORKTREE_BASE"] = str(tmp_path / "worktrees")

    r = _run_ps(
        SCRIPT,
        "-RepoRoot",
        str(clone),
        "-PruneClosedJobs",
        "-MaxExtraJobTrees",
        "-1",
        "-SkipSeatDisk",
        "-MaxJobStateLookups",
        "50",
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out

    assert dirty.is_dir(), "dirty fr-7999-shaped tree must survive"
    assert untracked.is_dir(), "untracked-only tree must survive"
    assert unpushed_no_up.is_dir(), "unpushed without upstream must survive"
    assert unpushed_up.is_dir(), "unpushed with upstream must survive"
    assert corrupt.is_dir(), "corrupted .git must survive"
    assert open_job.is_dir(), "open job must survive"
    assert not closed_job.is_dir(), f"closed clean job must prune\n{out}"
    assert not merged_head.is_dir(), f"merged headRefOid tree must prune\n{out}"
    assert "kept-dirty" in out or "keep dirty" in out.lower()
    _ = closed_oid  # publication via origin after fetch


@WIN
def test_fr8023_failed_fetch_zero_removals(tmp_path: Path):
    bare, clone = _init_bare_and_clone(tmp_path / "repo")
    closed = tmp_path / "fr-8023"
    _add_wt(clone, closed, "fr-8023")
    _seat_marker(closed, 8023)
    _push_branch(closed, "fr-8023")
    # Break origin so fetch fails.
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "missing-origin.git"))

    gh_bin = _write_gh_stub(
        tmp_path / "ghbin",
        {"issue:8023": {"json": json.dumps({"state": "CLOSED"})}},
    )
    env = os.environ.copy()
    env["PATH"] = str(gh_bin) + os.pathsep + env.get("PATH", "")

    r = _run_ps(
        SCRIPT,
        "-RepoRoot",
        str(clone),
        "-PruneClosedJobs",
        "-MaxExtraJobTrees",
        "-1",
        "-SkipSeatDisk",
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, out
    assert closed.is_dir(), "failed fetch must keep trees"
    assert "zero removals" in out.lower() or "removed=0" in out
    _ = bare


@WIN
def test_fr8023_gh_failure_keeps_clean_tree(tmp_path: Path):
    bare, clone = _init_bare_and_clone(tmp_path / "repo")
    closed = tmp_path / "fr-8023"
    _add_wt(clone, closed, "fr-8023")
    _seat_marker(closed, 8023)
    _push_branch(closed, "fr-8023")
    gh_bin = _write_gh_stub(tmp_path / "ghbin", {"issue:8023": {"exit": 1}})
    env = os.environ.copy()
    env["PATH"] = str(gh_bin) + os.pathsep + env.get("PATH", "")
    r = _run_ps(
        SCRIPT,
        "-RepoRoot",
        str(clone),
        "-PruneClosedJobs",
        "-MaxExtraJobTrees",
        "-1",
        "-SkipSeatDisk",
        env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert closed.is_dir()
    _ = bare


@WIN
def test_fr8023_seatdisk_skips_temp_with_git(tmp_path: Path):
    temp = tmp_path / "temp"
    temp.mkdir()
    aged = temp / "bobiverse-fr8023-aged"
    aged.mkdir()
    (aged / ".git").write_text("gitdir: somewhere\n", encoding="utf-8")
    (aged / "keep.txt").write_text("x\n", encoding="utf-8")
    # Age the directory
    old = 3 * 24 * 3600
    os.utime(aged, (os.path.getmtime(aged) - old, os.path.getmtime(aged) - old))

    env = os.environ.copy()
    # SeatDisk uses $env:TEMP by default via param; pass -TempRoot
    r = _run_ps(
        SEAT_DISK,
        "-Reclaim",
        "-TempRoot",
        str(temp),
        "-KeepTempHours",
        "1",
        "-MinFreeGB",
        "1000",
        "-GrokHome",
        str(tmp_path / "grok"),
        env=env,
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert aged.is_dir(), out
    assert (aged / ".git").exists()
    assert "FR #8023" in out or ".git" in out.lower()
