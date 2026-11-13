"""MRB #6919 hostile pin: FR #6918 live --job-worktree rewrite stays on main."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_mrb6919_refresh_live_skill_dag_mcp_files_callable():
    assert callable(bw.refresh_live_skill_dag_mcp_files)


def test_mrb6919_assign_hook_and_cleanup_exist_on_worker_seat():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "_refresh_live_skill_dag_mcp" in src
    assert "_live_skill_dag_job_end_cleanup" in src
    assert "refresh_live_skill_dag_mcp_files" in src
    assert "project_dir_for_assign" in src


def test_mrb6919_job_end_clears_job_worktree(tmp_path: Path):
    install = tmp_path / "install" / "worker"
    (install / ".grok" / "skills").mkdir(parents=True)
    (install / "bob" / ".grok" / "skills").mkdir(parents=True)
    (install / "common" / ".grok" / "skills").mkdir(parents=True)
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "skill_dag_mcp.py").write_text("# pin\n", encoding="utf-8")
    # point vision roots relative to worker by using worker as install/worker layout
    # skill_dag_vision_roots walks parents from worker_cwd
    bound = tmp_path / "bound"
    bound.mkdir()
    w = tmp_path / "job-w"
    (w / ".grok" / "skills").mkdir(parents=True)

    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=install,
        vision_cwd=install,
        job_worktree=w,
    )
    ptr = bound / ".grok" / "skill-dag-job-worktree"
    assert w.as_posix() in ptr.read_text(encoding="utf-8").replace("\\", "/")
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=install,
        vision_cwd=install,
        job_worktree=None,
    )
    assert ptr.read_text(encoding="utf-8").strip() == ""
