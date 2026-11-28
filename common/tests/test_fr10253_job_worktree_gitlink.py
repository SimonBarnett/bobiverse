"""FR #10253: detect and repair a job worktree whose .git gitfile points at a missing admin dir."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from repo_layout import ROOT

import sys

sys.path.insert(0, str(ROOT / "common" / "scripts"))

import job_worktree_gitlink as gl  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
    )
    out = subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return out.stdout.strip()


@pytest.fixture()
def repo_with_wt(tmp_path: Path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "main")
    (main / "README.md").write_text("x\n", encoding="utf-8")
    _git(main, "add", "README.md")
    _git(main, "commit", "-q", "-m", "init")
    wt = tmp_path / "wt" / "fr-10253"
    wt.parent.mkdir(parents=True)
    _git(main, "worktree", "add", "-q", "-b", "fr-10253", str(wt))
    return main, wt


def test_healthy_worktree_has_no_problem(repo_with_wt):
    _main, wt = repo_with_wt
    assert gl.gitlink_problem(wt) is None


def test_main_checkout_with_git_dir_is_not_a_problem(repo_with_wt):
    main, _wt = repo_with_wt
    assert gl.gitlink_problem(main) is None


def test_missing_admin_dir_is_reported(repo_with_wt):
    main, wt = repo_with_wt
    admin = main / ".git" / "worktrees" / "fr-10253"
    shutil.rmtree(admin)
    problem = gl.gitlink_problem(wt)
    assert problem is not None
    assert problem.startswith("gitdir-missing:")


def test_missing_git_file_is_reported(tmp_path: Path):
    wt = tmp_path / "bare-wt"
    wt.mkdir()
    assert gl.gitlink_problem(wt) == "git-missing"


def test_repair_recreates_admin_dir_and_restores_branch(repo_with_wt):
    main, wt = repo_with_wt
    (wt / "untracked.txt").write_text("keep me\n", encoding="utf-8")
    shutil.rmtree(main / ".git" / "worktrees" / "fr-10253")
    assert gl.gitlink_problem(wt) is not None

    status = gl.repair_gitlink(wt, branch="fr-10253")

    assert status == "repaired"
    assert gl.gitlink_problem(wt) is None
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "fr-10253"
    assert (wt / "untracked.txt").read_text(encoding="utf-8") == "keep me\n"
    assert "fr-10253" in _git(main, "worktree", "list")


def test_repair_refuses_without_branch(repo_with_wt):
    main, wt = repo_with_wt
    shutil.rmtree(main / ".git" / "worktrees" / "fr-10253")
    assert gl.repair_gitlink(wt, branch="").startswith("refused:")
    assert gl.gitlink_problem(wt) is not None


def test_repair_refuses_when_common_dir_missing(tmp_path: Path):
    wt = tmp_path / "orphan"
    wt.mkdir()
    (wt / ".git").write_text(
        "gitdir: " + str(tmp_path / "nowhere" / ".git" / "worktrees" / "orphan") + "\n",
        encoding="utf-8",
    )
    assert gl.repair_gitlink(wt, branch="fr-1").startswith("refused:")


def test_repair_is_noop_on_healthy_worktree(repo_with_wt):
    _main, wt = repo_with_wt
    assert gl.repair_gitlink(wt, branch="fr-10253") == "ok"
