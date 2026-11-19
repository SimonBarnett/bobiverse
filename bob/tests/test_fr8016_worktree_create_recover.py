"""FR #8016: recover stale worktree hold; NACK includes redacted git stderr."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))

import opencode_seat_contract as c  # noqa: E402


def _init_clone(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    (path / "README").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "README"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "i"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", str(path)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "fetch", "origin", "main"],
        check=True,
        capture_output=True,
    )
    return path


def _publish_branch(clone: Path, branch: str) -> str:
    subprocess.run(
        ["git", "-C", str(clone), "checkout", "-b", branch],
        check=True,
        capture_output=True,
    )
    (clone / "HEAD.txt").write_text(branch + "\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "add", "HEAD.txt"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(clone), "commit", "-m", branch],
        check=True,
        capture_output=True,
    )
    oid = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    subprocess.run(
        ["git", "-C", str(clone), "checkout", "main"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "fetch", "origin", branch],
        check=True,
        capture_output=True,
    )
    return oid


def _run_with_gh(head: str, oid: str):
    def run(cmd, **kw):
        if cmd and cmd[0] == "gh":
            class Proc:
                returncode = 0
                stdout = json.dumps(
                    {
                        "headRefName": head,
                        "headRefOid": oid,
                        "isCrossRepository": False,
                    }
                )
                stderr = ""

            return Proc()
        return subprocess.run(cmd, **kw)

    return run


def test_stale_worktree_holding_branch_recovers_once(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_branch(clone, "fr-8002")
    stale = tmp_path / "stale-mrb"
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", str(stale), "fr-8002"],
        check=True,
        capture_output=True,
    )
    # Dead pid marker so prune is safe (not a live sibling seat).
    (stale / ".bobiverse-seat").write_text(
        json.dumps({"nick": "old-seat", "pid": 1, "issue": 8006, "repo": "SimonBarnett/bobiverse"}),
        encoding="utf-8",
    )
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    ready = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    assert ready["state"] == "project", ready
    assert Path(ready["path"]).is_dir()
    head = subprocess.run(
        ["git", "-C", str(ready["path"]), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid
    assert not stale.is_dir()


def test_dirty_holder_nacks_with_stderr_not_destroyed(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_branch(clone, "fr-8002")
    holder = tmp_path / "dirty-mrb"
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", str(holder), "fr-8002"],
        check=True,
        capture_output=True,
    )
    (holder / "WIP.txt").write_text("keep me\n", encoding="utf-8")
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    decision = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    # FR #8326: dirty author tree stays, but the review tree is still created
    # at the PR head on mrb-<n>-review (do not NACK dirty / head-mismatch).
    assert decision["state"] == "project", decision
    assert holder.is_dir()
    assert (holder / "WIP.txt").read_text(encoding="utf-8") == "keep me\n"
    head = subprocess.run(
        ["git", "-C", str(decision["path"]), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid
    branch = subprocess.run(
        ["git", "-C", str(decision["path"]), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "mrb-8006-review"


def test_git_worktree_nack_includes_redacted_stderr(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: FR SimonBarnett/bobiverse#8016 https://x"
    base = subprocess.run

    def run(cmd, **kw):
        if cmd and cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            class Proc:
                returncode = 128
                stdout = ""
                stderr = (
                    "fatal: could not create worktree "
                    "token=github_pat_EXAMPLEONLY0000000000000000000000000000\n"
                )

            return Proc()
        return base(cmd, **kw)

    decision = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=run, nick="flamingo-1"
    )
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:git-worktree" in decision["nack"]
    assert "could not create worktree" in decision["nack"]
    assert "github_pat_" not in decision["nack"]
    assert "[REDACTED]" in decision["nack"]


def test_redact_git_detail_collapses_and_truncates():
    raw = "fatal: oops\n  path=C:\\Users\\x\\wt\n\n"
    out = c.redact_git_detail(raw, max_len=40)
    assert "\n" not in out
    assert len(out) <= 40
