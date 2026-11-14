"""FR #7308: assign refresh must not rewrite MCP config (Grok/Cursor would drop stdio)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr7308_refresh_does_not_rewrite_toml_or_mcp_json(tmp_path: Path):
    worker = tmp_path / "install" / "worker"
    for p in (
        worker / ".grok" / "skills",
        tmp_path / "install" / "bob" / ".grok" / "skills",
        tmp_path / "install" / "common" / ".grok" / "skills",
        worker / "scripts",
    ):
        p.mkdir(parents=True)
    (worker / "scripts" / "skill_dag_mcp.py").write_text("# mcp\n", encoding="utf-8")
    bound = tmp_path / "bound-cwd"
    bound.mkdir()
    bw.write_skill_dag_mcp_config(str(bound), job_worktree=None, vision_cwd=str(worker))
    bw.write_cursor_skill_dag_mcp_config(str(worker), job_worktree=None)
    toml = bound / ".grok" / "config.toml"
    mcp = worker / ".cursor" / "mcp.json"
    toml_text = toml.read_text(encoding="utf-8")
    mcp_text = mcp.read_text(encoding="utf-8")
    toml_mtime = toml.stat().st_mtime_ns
    mcp_mtime = mcp.stat().st_mtime_ns
    job = tmp_path / "job-wt"
    (job / ".grok" / "skills").mkdir(parents=True)
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=worker,
        vision_cwd=worker,
        job_worktree=job,
    )
    assert toml.read_text(encoding="utf-8") == toml_text
    assert mcp.read_text(encoding="utf-8") == mcp_text
    assert toml.stat().st_mtime_ns == toml_mtime
    assert mcp.stat().st_mtime_ns == mcp_mtime
    grok_ptr = (bound / ".grok" / "skill-dag-job-worktree").read_text(encoding="utf-8")
    cur_ptr = (worker / ".grok" / "skill-dag-job-worktree").read_text(encoding="utf-8")
    assert job.as_posix() in grok_ptr.replace("\\", "/")
    assert job.as_posix() in cur_ptr.replace("\\", "/")


def test_fr7308_pointer_write_skips_identical(tmp_path: Path):
    cwd = tmp_path / "seat"
    job = tmp_path / "wt"
    job.mkdir()
    p = bw.write_skill_dag_job_worktree_pointer(cwd, job)
    m0 = p.stat().st_mtime_ns
    bw.write_skill_dag_job_worktree_pointer(cwd, job)
    assert p.stat().st_mtime_ns == m0


def test_fr7308_drop_check_does_not_use_job_path_as_cmdline_marker():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    i = src.index("def _refresh_live_skill_dag_mcp")
    chunk = src[i : i + 1800]
    assert "keep the live stdio MCP" in chunk
    assert "restart_skill_dag_mcp_stdio_children" not in chunk
    assert "markers = [bound, cursor, vision, job_worktree]" not in chunk
    assert "FR #7308" in chunk or "job-worktree-file only" in chunk.lower() or "pointer file" in chunk
