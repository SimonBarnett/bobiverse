"""FR #7446: skill-dag job-worktree pointer must not live inside Grok bound-cwd."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import skill_dag_bound as bound


def test_fr7446_bound_pointer_is_sibling_of_bound_cwd(tmp_path: Path):
    run = tmp_path / "run"
    b = run / "bound-cwd"
    b.mkdir(parents=True)
    p = bw.skill_dag_job_worktree_pointer_path(b)
    assert p == run / "skill-dag-job-worktree"
    assert p.parent == b.parent
    assert "bound-cwd" not in p.parts


def test_fr7446_refresh_does_not_touch_bound_cwd_tree(tmp_path: Path):
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
    grok_bound = run / "bound-cwd"
    grok_bound.mkdir(parents=True)
    # Launch still clears a pre-#7446 in-workspace pointer. Assign refresh must not.
    legacy = grok_bound / "skill-dag-job-worktree"
    legacy.write_text("old\n", encoding="utf-8")
    bw.write_skill_dag_mcp_config(str(grok_bound), job_worktree=None, vision_cwd=str(worker))
    assert not legacy.exists()
    legacy.write_text("stale-while-agent-up\n", encoding="utf-8")
    cfg = grok_bound / ".grok" / "config.toml"
    cfg_text = cfg.read_text(encoding="utf-8")
    cfg_mtime = cfg.stat().st_mtime_ns
    job = tmp_path / "job-wt"
    (job / ".grok" / "skills").mkdir(parents=True)
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=grok_bound,
        cursor_cwd=worker,
        vision_cwd=worker,
        job_worktree=job,
    )
    assert cfg.read_text(encoding="utf-8") == cfg_text
    assert cfg.stat().st_mtime_ns == cfg_mtime
    assert legacy.is_file(), "assign refresh must not delete inside bound-cwd (FR #7664)"
    assert legacy.read_text(encoding="utf-8") == "stale-while-agent-up\n"
    ptr = run / "skill-dag-job-worktree"
    assert job.as_posix() in ptr.read_text(encoding="utf-8").replace("\\", "/")
    assert bw.BOB_SKILL_MCP_URL in cfg_text
    assert "skill_dag_mcp.py" not in cfg_text


def test_fr7446_launch_args_include_seat_cwd_marker(tmp_path: Path):
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills").mkdir(parents=True)
    (worker / "scripts").mkdir(parents=True)
    (worker / "scripts" / "skill_dag_mcp.py").write_text("# mcp\n", encoding="utf-8")
    bound_cwd = tmp_path / "run" / "bound-cwd"
    bound_cwd.mkdir(parents=True)
    args = bw.skill_dag_mcp_launch_args(str(worker), job_worktree=None, pointer_cwd=bound_cwd)
    assert "--job-worktree-file" in args
    ptr = args[args.index("--job-worktree-file") + 1]
    assert ptr.replace("\\", "/").endswith("/skill-dag-job-worktree")
    assert "bound-cwd" not in Path(ptr).parts
    assert "--seat-cwd" in args
    assert Path(args[args.index("--seat-cwd") + 1]) == bound_cwd
    assert bw.skill_dag_mcp_stdio_cmdline_matches(
        "python skill_dag_mcp.py " + " ".join(args),
        [str(bound_cwd)],
    )


def test_fr7446_bound_prepare_pointer_outside_workspace(tmp_path: Path):
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills").mkdir(parents=True)
    mcp = tmp_path / "skill_dag_mcp.py"
    mcp.write_text("# mcp\n", encoding="utf-8")
    run = tmp_path / "run"
    b = bound.prepare_bound_agent_cwd(run, worker, mcp_script=mcp)
    assert not (b / "skill-dag-job-worktree").exists()
    ptr = run / "skill-dag-job-worktree"
    assert ptr.is_file()
    toml = (b / ".grok" / "config.toml").read_text(encoding="utf-8")
    assert "https://bob.ntsa.uk/mcp" in toml
    assert "skill_dag_mcp.py" not in toml
