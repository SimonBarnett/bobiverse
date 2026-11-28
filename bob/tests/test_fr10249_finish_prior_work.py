"""FR #10249: FINISH/assign text must not claim prior work the worktree does not hold."""
from __future__ import annotations

import subprocess
from pathlib import Path

import bob_worker as bw

KEY = "FR SimonBarnett/bobiverse#10235"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repo_with_origin_main(tmp_path: Path) -> Path:
    repo = tmp_path / "wt"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "base")
    # Pretend origin/main points at the base commit.
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def test_fr10249_clean_worktree_has_no_prior_work(tmp_path: Path):
    repo = _repo_with_origin_main(tmp_path)
    assert bw.opencode_worktree_prior_work(repo) is False
    text = bw.opencode_job_finish_steps(
        job_key=KEY, worktree=str(repo), outbox=str(repo / ".bob" / "outbox.txt")
    )
    assert "Work so far is already" not in text
    assert "No prior work" in text
    assert "from scratch" in text


def test_fr10249_dirty_worktree_has_prior_work(tmp_path: Path):
    repo = _repo_with_origin_main(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    assert bw.opencode_worktree_prior_work(repo) is True
    text = bw.opencode_job_finish_steps(
        job_key=KEY, worktree=str(repo), outbox=str(repo / ".bob" / "outbox.txt")
    )
    assert "Prior work is in the worktree" in text
    assert "from scratch" not in text


def test_fr10249_commit_ahead_of_origin_main_is_prior_work(tmp_path: Path):
    repo = _repo_with_origin_main(tmp_path)
    (repo / "a.txt").write_text("two\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "c2")
    assert bw.opencode_worktree_prior_work(repo) is True


def test_fr10249_unknown_worktree_is_not_claimed(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    assert bw.opencode_worktree_prior_work(missing) is None
    text = bw.opencode_job_finish_steps(
        job_key=KEY, worktree=str(missing), outbox=str(tmp_path / "o.txt")
    )
    assert "Work so far is already" not in text
    assert "Could not verify prior work" in text


def test_fr10249_finish_steps_mention_rg_fallback(tmp_path: Path):
    text = bw.opencode_job_finish_steps(
        job_key=KEY, worktree=str(tmp_path), outbox=str(tmp_path / "o.txt")
    )
    assert "ripgrep (rg) may not be on PATH" in text
