"""FR #8572: clear stale job gitdir index.lock; allowlist gitdir for OpenCode."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def _linked_worktree(tmp_path: Path, name: str = "fix-8561") -> tuple[Path, Path]:
    """Create a linked-worktree shape: job/.git file -> install/.git/worktrees/<name>."""
    install = tmp_path / "install"
    git_wt = install / ".git" / "worktrees" / name
    git_wt.mkdir(parents=True)
    job = tmp_path / "worktrees" / "bobiverse" / name
    job.mkdir(parents=True)
    (job / ".git").write_text(f"gitdir: {git_wt.as_posix()}\n", encoding="utf-8")
    return job, git_wt


def test_fr8572_resolve_job_git_dir_linked(tmp_path):
    job, git_wt = _linked_worktree(tmp_path)
    assert bw.resolve_job_git_dir(job) == git_wt.resolve()


def test_fr8572_clear_stale_index_lock(tmp_path):
    job, git_wt = _linked_worktree(tmp_path)
    lock = git_wt / "index.lock"
    lock.write_text("stale\n", encoding="utf-8")
    logs: list[str] = []
    assert bw.clear_stale_job_index_lock(job, log_fn=logs.append) is True
    assert not lock.exists()
    assert any("cleared stale index.lock" in line for line in logs)


def test_fr8572_clear_noop_when_absent(tmp_path):
    job, _git_wt = _linked_worktree(tmp_path)
    assert bw.clear_stale_job_index_lock(job) is False


def test_fr8572_gitdir_patterns_include_index_lock(tmp_path):
    job, git_wt = _linked_worktree(tmp_path)
    patterns = bw.opencode_job_gitdir_read_patterns(job)
    joined = "\n".join(patterns)
    assert str(git_wt.resolve()) in joined or git_wt.as_posix() in joined
    assert any(p.endswith("index.lock") or p.endswith("index.lock".replace("/", "\\")) for p in patterns)


def test_fr8572_mcp_document_allows_gitdir(tmp_path):
    job, git_wt = _linked_worktree(tmp_path)
    worker = tmp_path / "bob" / "worker"
    worker.mkdir(parents=True)
    doc = bw.opencode_skill_dag_mcp_document(str(worker), job_worktree=job)
    allow = doc["permission"]["external_directory"]
    assert any(
        str(git_wt.resolve()) in key or git_wt.as_posix() in key
        for key, val in allow.items()
        if val == "allow"
    )


def test_fr8572_opencode_ready_calls_clear_preflight():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "clear_stale_job_index_lock(prepared[\"path\"]" in src.replace("'", '"') or (
        "clear_stale_job_index_lock(prepared['path']" in src
    )
    assert "FR #8572" in src
