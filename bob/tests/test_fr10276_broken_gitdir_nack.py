"""FR #10276: a job worktree with broken linked-worktree git metadata is NACKed, not ACKed."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "bob" / "scripts"))
sys.path.insert(0, str(REPO / "common" / "scripts"))

import opencode_seat_contract as c  # noqa: E402

LINE = "FROM jeeves #marchhare n: FR SimonBarnett/bobiverse#10276 https://x"


def _linked_wt(env: dict, *, drop: str = "") -> Path:
    """Create the assigned job tree as a linked worktree; *drop* removes one metadata file."""
    path = Path(c.project_dir_for_assign(LINE, env))
    common = path.parent / "common-git" / ".git"
    meta = common / "worktrees" / path.name
    meta.mkdir(parents=True)
    (common / "info").mkdir()
    for name, text in (
        ("HEAD", "ref: refs/heads/fr-10276\n"),
        ("gitdir", str(path / ".git") + "\n"),
        ("commondir", "../..\n"),
    ):
        if name != drop:
            (meta / name).write_text(text, encoding="utf-8")
    path.mkdir(parents=True)
    (path / ".git").write_text(f"gitdir: {meta.as_posix()}\n", encoding="utf-8")
    return path


def test_broken_metadata_is_nacked_before_ack(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    _linked_wt(env, drop="HEAD")
    decision = c.ensure_opencode_job_worktree(LINE, env)
    assert decision["state"] == "create_failed"
    assert decision["nack"].startswith("NACK FR SimonBarnett/bobiverse#10276 ")
    assert "worktree-create-failed:broken-gitdir" in decision["nack"]
    assert "worktree metadata incomplete" in decision["nack"]
    assert decision["error_class"] == "broken-gitdir"


def test_missing_gitfile_target_is_nacked(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    path = _linked_wt(env)
    (path / ".git").write_text("gitdir: C:/nonexistent/worktrees/x\n", encoding="utf-8")
    decision = c.ensure_opencode_job_worktree(LINE, env)
    assert decision["state"] == "create_failed"
    assert "worktree-create-failed:broken-gitdir" in decision["nack"]


def test_healthy_linked_worktree_still_projects(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    _linked_wt(env)
    decision = c.ensure_opencode_job_worktree(LINE, env)
    assert decision["state"] == "project"
    assert decision["nack"] == ""


def test_plain_directory_without_git_is_not_flagged(tmp_path: Path):
    env = {"BOB_JOB_WORKTREE_BASE": str(tmp_path / "worktrees")}
    Path(c.project_dir_for_assign(LINE, env)).mkdir(parents=True)
    assert c.broken_linked_worktree_reason(c.project_dir_for_assign(LINE, env)) == ""
    decision = c.ensure_opencode_job_worktree(LINE, env)
    assert decision["state"] == "project"


def test_empty_path_is_not_flagged():
    assert c.broken_linked_worktree_reason("") == ""
