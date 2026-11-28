"""FR #7361: job-worktree pointer lives outside ``.grok`` so Grok does not drop stdio MCP."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import skill_dag_bound as bound


def test_fr7361_pointer_path_is_not_under_grok():
    cwd = Path("C:/seat/bound-cwd")
    p = bw.skill_dag_job_worktree_pointer_path(cwd)
    # FR #7446: also outside bound-cwd itself (Grok watches the workspace root).
    assert p == cwd.parent / "skill-dag-job-worktree"
    assert ".grok" not in p.parts
    assert p.parent == cwd.parent


def test_fr7361_refresh_does_not_touch_grok_dir(tmp_path: Path):
    worker = tmp_path / "install" / "worker"
    for p in (
        worker / ".grok" / "skills",
        tmp_path / "install" / "bob" / ".grok" / "skills",
        tmp_path / "install" / "common" / ".grok" / "skills",
        worker / "scripts",
    ):
        p.mkdir(parents=True)
    (worker / "scripts" / "skill_dag_mcp.py").write_text("# mcp\n", encoding="utf-8")
    grok_bound = tmp_path / "bound-cwd"
    grok_bound.mkdir()
    bw.write_skill_dag_mcp_config(str(grok_bound), job_worktree=None, vision_cwd=str(worker))
    grok = grok_bound / ".grok"
    cfg = grok / "config.toml"
    cfg_text = cfg.read_text(encoding="utf-8")
    cfg_mtime = cfg.stat().st_mtime_ns
    grok_mtime = grok.stat().st_mtime_ns
    names_before = sorted(p.name for p in grok.iterdir())
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
    assert grok.stat().st_mtime_ns == grok_mtime
    assert sorted(p.name for p in grok.iterdir()) == names_before
    assert not (grok / "skill-dag-job-worktree").exists()
    assert not (grok_bound / "skill-dag-job-worktree").exists()
    ptr = grok_bound.parent / "skill-dag-job-worktree"
    assert job.as_posix() in ptr.read_text(encoding="utf-8").replace("\\", "/")
    assert bw.BOB_SKILL_MCP_URL in cfg_text
    assert "skill_dag_mcp.py" not in cfg_text


def test_fr7361_bound_prepare_pointer_outside_grok(tmp_path: Path):
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills").mkdir(parents=True)
    mcp = tmp_path / "skill_dag_mcp.py"
    mcp.write_text("# mcp\n", encoding="utf-8")
    run = tmp_path / "run"
    b = bound.prepare_bound_agent_cwd(run, worker, mcp_script=mcp)
    grok = b / ".grok"
    assert (grok / "config.toml").is_file()
    assert not (grok / "skill-dag-job-worktree").exists()
    assert not (b / "skill-dag-job-worktree").exists()
    ptr = b.parent / "skill-dag-job-worktree"
    assert ptr.is_file()
    toml = (grok / "config.toml").read_text(encoding="utf-8")
    assert bw.BOB_SKILL_MCP_URL in toml
    assert "skill_dag_mcp.py" not in toml
    grok_mtime = grok.stat().st_mtime_ns
    cfg_mtime = (grok / "config.toml").stat().st_mtime_ns
    job = tmp_path / "wt"
    job.mkdir()
    bw.write_skill_dag_job_worktree_pointer(b, job)
    assert grok.stat().st_mtime_ns == grok_mtime
    assert (grok / "config.toml").stat().st_mtime_ns == cfg_mtime
    assert not (b / "skill-dag-job-worktree").exists()
    assert job.as_posix() in ptr.read_text(encoding="utf-8").replace("\\", "/")
