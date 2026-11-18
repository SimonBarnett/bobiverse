"""FR #8022: MRB worktree HEAD must equal gh pr view headRefOid (never main)."""
from __future__ import annotations

import json
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


def _publish_head(clone: Path, branch: str) -> str:
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
    subprocess.run(
        ["git", "-C", str(clone), "branch", "-D", branch],
        check=True,
        capture_output=True,
    )
    return oid


def _main_oid(clone: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "origin/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def _run_with_gh(head: str | None, oid: str | None, *, gh_code: int = 0, cross: bool = False):
    def run(cmd, **kw):
        if cmd and cmd[0] == "gh":
            class Proc:
                returncode = gh_code
                stdout = (
                    ""
                    if gh_code
                    else json.dumps(
                        {
                            "headRefName": head or "",
                            "headRefOid": oid or "",
                            "isCrossRepository": cross,
                        }
                    )
                )
                stderr = "" if gh_code == 0 else "missing"

            return Proc()
        return subprocess.run(cmd, **kw)

    return run


def test_mrb_worktree_head_equals_headrefoid_not_main(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_head(clone, "fr-8002")
    main = _main_oid(clone)
    assert oid != main
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
    path = Path(ready["path"])
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid
    assert head != main
    assert c.worktree_reviewed_sha(path) == oid


def test_mrb_create_uses_sha_start_point(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_head(clone, "fr-8002")
    seen: list[list[str]] = []
    base = _run_with_gh("fr-8002", oid)

    def run(cmd, **kw):
        if cmd and cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            seen.append(list(cmd))
        return base(cmd, **kw)

    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    ready = c.ensure_opencode_job_worktree(
        line, env, install_root=str(clone), run=run, nick="flamingo-1"
    )
    assert ready["state"] == "project"
    assert seen
    add = seen[-1]
    assert "-B" in add
    assert oid in add
    assert "origin/main" not in add


def test_mrb_reuse_refreshes_stale_clean_tree(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_head(clone, "fr-8002")
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    first = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    assert first["state"] == "project"
    path = Path(first["path"])
    # Move tree to main (wrong tip) while keeping it clean and linked.
    subprocess.run(
        ["git", "-C", str(path), "checkout", "-B", "fr-8002", "origin/main"],
        check=True,
        capture_output=True,
    )
    assert (
        subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        == _main_oid(clone)
    )
    second = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    assert second["state"] == "project", second
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid


def test_mrb_reuse_nacks_dirty_stale_tree(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_head(clone, "fr-8002")
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    first = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    path = Path(first["path"])
    subprocess.run(
        ["git", "-C", str(path), "checkout", "-B", "fr-8002", "origin/main"],
        check=True,
        capture_output=True,
    )
    (path / "dirty.txt").write_text("nope\n", encoding="utf-8")
    second = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    assert second["state"] == "create_failed"
    assert "worktree-create-failed:stale-dirty" in second["nack"]


def test_mrb_missing_oid_nacks_pr_head(tmp_path: Path):
    clone = _init_clone(tmp_path / "clone")
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    decision = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", ""),
    )
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:pr-head" in decision["nack"]


def test_mrb_refresh_detaches_when_pr_branch_is_busy(tmp_path: Path):
    """FR #8233: checkout -B fails if a sibling holds the PR branch; detach at headRefOid."""
    clone = _init_clone(tmp_path / "clone")
    oid = _publish_head(clone, "fr-8002")
    main = _main_oid(clone)
    env = {
        "BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees"),
        "BOB_REPO_CLONE_bobiverse": str(clone),
    }
    line = "FROM jeeves #flamingo n: MRB SimonBarnett/bobiverse#8006 https://x"
    first = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    path = Path(first["path"])
    subprocess.run(
        ["git", "-C", str(path), "checkout", "-B", "holder-wrong", "origin/main"],
        check=True,
        capture_output=True,
    )
    sibling = tmp_path / "sibling"
    subprocess.run(
        ["git", "-C", str(clone), "worktree", "add", str(sibling), "fr-8002"],
        check=True,
        capture_output=True,
    )
    second = c.ensure_opencode_job_worktree(
        line,
        env,
        install_root=str(clone),
        run=_run_with_gh("fr-8002", oid),
        nick="flamingo-1",
    )
    assert second["state"] == "project", second
    head = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()
    assert head == oid
    assert head != main
    stamp = (path / ".bob" / "reviewed-sha").read_text(encoding="utf-8").strip()
    assert stamp == oid
    branch = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "HEAD"
    sibling_branch = subprocess.run(
        ["git", "-C", str(sibling), "rev-parse", "--abbrev-ref", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert sibling_branch == "fr-8002"
