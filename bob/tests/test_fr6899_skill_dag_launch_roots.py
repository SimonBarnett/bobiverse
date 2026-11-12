"""FR #6899: Grok/Cursor skill-dag MCP argv uses vision --root packs, not script-adjacent default."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bob_worker as bw
import skill_dag_mcp as mcp


def _tree(tmp_path: Path) -> dict[str, Path]:
    install = tmp_path / "install"
    worker = install / "worker"
    seat = worker / ".grok" / "skills"
    bobpack = install / ".grok" / "skills"
    harvest = install / "common" / ".grok" / "skills"
    scripts = install / "scripts"
    for p in (worker, seat, bobpack, harvest, scripts):
        p.mkdir(parents=True)
    (scripts / "skill_dag_mcp.py").write_text("# fixture mcp\n", encoding="utf-8")
    return {
        "install": install,
        "worker": worker,
        "seat": seat,
        "bobpack": bobpack,
        "harvest": harvest,
    }


def test_fr6899_grok_and_cursor_mcp_args_include_seat_and_harvest_roots(tmp_path):
    t = _tree(tmp_path)
    run = tmp_path / "run"
    run.mkdir()
    grok = bw.build_launch(
        "grok",
        "agent",
        str(t["worker"]),
        "prompt",
        "grok.exe",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    cur = bw.build_launch(
        "cursor",
        "agent",
        str(t["worker"]),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    for spec in (grok, cur):
        args = spec.skill_dag_mcp_args
        joined = " ".join(args)
        assert "skill_dag_mcp.py" in joined
        assert "--root" in args
        assert t["seat"].as_posix() in args
        assert t["harvest"].as_posix() in args


def test_fr6899_job_worktree_launch_adds_only_that_skills_root(tmp_path):
    t = _tree(tmp_path)
    job = tmp_path / "job-wt"
    (job / ".grok" / "skills").mkdir(parents=True)
    sibling = tmp_path / "sibling-repo" / ".grok" / "skills"
    sibling.mkdir(parents=True)
    args = bw.skill_dag_mcp_launch_args(str(t["worker"]), job_worktree=job)
    assert "--job-worktree" in args
    assert Path(job).as_posix() in args or str(job) in args
    parsed = mcp.roots_from_argv(args[1:])
    job_skills = (job / ".grok" / "skills").resolve()
    assert any(p.resolve() == job_skills for p in parsed)
    with pytest.raises(mcp.JobSkillsRootRefused):
        mcp.accept_job_skills_root(sibling, assigned_worktree=job)


def test_fr6899_refresh_replaces_stale_skill_dag_args(tmp_path):
    t = _tree(tmp_path)
    cfg = t["worker"] / ".grok" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(
        '[mcp_servers.skill-dag]\ncommand = "python"\nargs = ["old.py"]\n',
        encoding="utf-8",
    )
    bw.write_skill_dag_mcp_config(str(t["worker"]))
    body = cfg.read_text(encoding="utf-8")
    assert "old.py" not in body
    assert "--root" in body
    assert "skill_dag_mcp.py" in body
