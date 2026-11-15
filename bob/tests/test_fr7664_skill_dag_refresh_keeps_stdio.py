"""FR #7664: assign refresh writes the outside pointer and leaves the stdio child alone."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr7664_refresh_does_not_unlink_legacy_pointer(tmp_path: Path):
    worker = tmp_path / "install" / "worker"
    for p in (
        worker / ".grok" / "skills",
        tmp_path / "install" / "bob" / ".grok" / "skills",
        tmp_path / "install" / "common" / ".grok" / "skills",
        worker / "scripts",
    ):
        p.mkdir(parents=True)
    (worker / "scripts" / "skill_dag_mcp.py").write_text("# mcp\n", encoding="utf-8")
    run = tmp_path / "run"
    bound = run / "bound-cwd"
    bound.mkdir(parents=True)
    bw.write_skill_dag_mcp_config(str(bound), job_worktree=None, vision_cwd=str(worker))
    legacy = bound / "skill-dag-job-worktree"
    legacy.write_text("leave-me\n", encoding="utf-8")
    names = sorted(p.name for p in bound.rglob("*"))
    job = tmp_path / "job-wt"
    (job / ".grok" / "skills").mkdir(parents=True)
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=None,
        vision_cwd=worker,
        job_worktree=job,
    )
    assert legacy.read_text(encoding="utf-8") == "leave-me\n"
    assert sorted(p.name for p in bound.rglob("*")) == names
    ptr = run / "skill-dag-job-worktree"
    assert job.as_posix() in ptr.read_text(encoding="utf-8").replace("\\", "/")


def test_fr7664_once_is_not_the_stdio_child():
    seat = "C:/run/bound-cwd"
    once = f"python skill_dag_mcp.py --once resolve --seat-cwd {seat}"
    live = f"python skill_dag_mcp.py --job-worktree-file C:/run/skill-dag-job-worktree --seat-cwd {seat}"
    assert not bw.skill_dag_mcp_stdio_cmdline_matches(once, [seat])
    assert bw.skill_dag_mcp_stdio_cmdline_matches(live, [seat])


def test_fr7664_descendant_pids_skip_once():
    seat = "C:/run/bound-cwd"
    rows = [(10, 1), (11, 10), (12, 10)]

    def snap():
        return rows

    def cmd(pid: int) -> str:
        if pid == 11:
            return f"python skill_dag_mcp.py --once status --seat-cwd {seat}"
        if pid == 12:
            return f"python skill_dag_mcp.py --seat-cwd {seat}"
        return ""

    assert bw.skill_dag_mcp_descendant_pids(10, [seat], snapshot=snap, cmdline_of=cmd) == [12]
