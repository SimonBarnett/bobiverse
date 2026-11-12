"""FR #6928: after MCP file rewrite, restart this seat's skill-dag stdio child."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr6928_cmdline_matches_seat_marker_not_sibling():
    script = "C:/ai/bob/scripts/skill_dag_mcp.py"
    seat = "C:/Users/x/AppData/Local/Bobiverse/worker/run/worker-flamingo-1/bound-cwd"
    other = "C:/Users/x/AppData/Local/Bobiverse/worker/run/worker-flamingo-2/bound-cwd"
    mine = f"python {script} --root {seat}/.grok/skills --job-worktree D:/jobs/W"
    sib = f"python {script} --root {other}/.grok/skills --job-worktree D:/jobs/W"
    assert bw.skill_dag_mcp_stdio_cmdline_matches(mine, [seat])
    assert not bw.skill_dag_mcp_stdio_cmdline_matches(sib, [seat])
    assert not bw.skill_dag_mcp_stdio_cmdline_matches("python other.py --root " + seat, [seat])


def test_fr6928_kills_descendant_mcp_not_foreign_or_agent():
    killed: list[int] = []
    # agent 10 -> mcp 20; foreign mcp 30 (other agent 11)
    rows = [
        (10, 1, "agent.exe"),
        (20, 10, "python.exe"),
        (11, 1, "agent.exe"),
        (30, 11, "python.exe"),
    ]
    seat = r"C:\seat-a\bound-cwd"
    cmds = {
        20: r'python C:\bob\scripts\skill_dag_mcp.py --root C:\seat-a\bound-cwd\.grok\skills --job-worktree D:\old',
        30: r'python C:\bob\scripts\skill_dag_mcp.py --root C:\seat-b\bound-cwd\.grok\skills',
        10: r"C:\fake\agent.exe",
    }
    got = bw.restart_skill_dag_mcp_stdio_children(
        10,
        [seat],
        snapshot=lambda: rows,
        cmdline_of=lambda pid: cmds.get(pid, ""),
        kill=lambda pid: killed.append(pid) or True,
    )
    assert got == [20]
    assert killed == [20]


def test_fr6928_refresh_then_restart_sees_new_job_worktree_in_planned_argv(tmp_path: Path):
    """Behaviour: rewrite files, then a respawn argv (skill_dag_mcp_launch_args) includes the new worktree.

    The kill step is what forces grok/cursor to spawn that argv; this pins the pair.
    """
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills").mkdir(parents=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "skill_dag_mcp.py").write_text("# mcp\n", encoding="utf-8")
    bound = tmp_path / "bound-cwd"
    bound.mkdir()
    job = tmp_path / "job-wt"
    (job / ".grok" / "skills").mkdir(parents=True)
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=worker,
        vision_cwd=worker,
        job_worktree=job,
    )
    args = bw.skill_dag_mcp_launch_args(str(worker), job_worktree=job)
    assert "--job-worktree" in args
    assert job.as_posix() in args or str(job) in args
    killed: list[int] = []
    bw.restart_skill_dag_mcp_stdio_children(
        99,
        [str(bound), str(worker)],
        snapshot=lambda: [(99, 1, "agent.exe"), (100, 99, "python.exe")],
        cmdline_of=lambda pid: (
            f"python skill_dag_mcp.py --root {bound.as_posix()}" if pid == 100 else "agent"
        ),
        kill=lambda pid: killed.append(pid) or True,
    )
    assert killed == [100]
