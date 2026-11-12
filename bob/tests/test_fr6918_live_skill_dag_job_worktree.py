"""FR #6918: grok bound config.toml and cursor mcp.json get --job-worktree on assign."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def _tree(tmp_path: Path) -> dict[str, Path]:
    install = tmp_path / "install"
    worker = install / "worker"
    seat = worker / ".grok" / "skills"
    bobpack = install / "bob" / ".grok" / "skills"
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


def _launch_grok_bound(tmp_path: Path) -> dict:
    t = _tree(tmp_path)
    run = tmp_path / "run" / "worker-x"
    run.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(t["worker"]),
        run_dir=run,
        machine="flamingo",
        nick="flamingo-1",
        agent_exe=r"C:\\fake\\agent.exe",
    )
    return {"tree": t, "run": run, "child": child}


def test_fr6918_start_has_no_job_worktree_flag(tmp_path):
    launched = _launch_grok_bound(tmp_path)
    grok_body = (Path(launched["child"]["cwd"]) / ".grok" / "config.toml").read_text(
        encoding="utf-8"
    )
    assert "--job-worktree" not in grok_body
    t = launched["tree"]
    run = tmp_path / "run-c"
    run.mkdir()
    cur = bw.build_launch(
        "cursor",
        "agent",
        str(t["worker"]),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    bw.write_cursor_skill_dag_mcp_config_if_agent(cur)
    cur_body = (Path(t["worker"]) / ".cursor" / "mcp.json").read_text(encoding="utf-8")
    assert "--job-worktree" not in cur_body
    for pack in (t["seat"], t["bobpack"], t["harvest"]):
        assert pack.as_posix() in grok_body.replace("\\", "/")
        assert pack.as_posix() in cur_body.replace("\\", "/")


def test_fr6918_assign_rewrites_only_assigned_worktree(tmp_path):
    launched = _launch_grok_bound(tmp_path)
    t = launched["tree"]
    bound = Path(launched["child"]["cwd"])
    w = tmp_path / "jobs" / "W"
    v = tmp_path / "jobs" / "V"
    sibling = tmp_path / "jobs" / "sibling"
    for p in (w, v, sibling):
        (p / ".grok" / "skills").mkdir(parents=True)

    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=t["worker"],
        vision_cwd=t["worker"],
        job_worktree=w,
    )
    grok_w = (bound / ".grok" / "config.toml").read_text(encoding="utf-8").replace("\\", "/")
    cur_w = (t["worker"] / ".cursor" / "mcp.json").read_text(encoding="utf-8").replace("\\", "/")
    assert "--job-worktree" in grok_w and w.as_posix() in grok_w
    assert "--job-worktree" in cur_w and w.as_posix() in cur_w
    assert sibling.as_posix() not in grok_w
    assert sibling.as_posix() not in cur_w
    assert t["harvest"].as_posix() in grok_w
    assert t["harvest"].as_posix() in cur_w

    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=t["worker"],
        vision_cwd=t["worker"],
        job_worktree=v,
    )
    grok_v = (bound / ".grok" / "config.toml").read_text(encoding="utf-8").replace("\\", "/")
    cur_v = (t["worker"] / ".cursor" / "mcp.json").read_text(encoding="utf-8").replace("\\", "/")
    assert w.as_posix() not in grok_v and v.as_posix() in grok_v
    assert w.as_posix() not in cur_v and v.as_posix() in cur_v

    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=bound,
        cursor_cwd=t["worker"],
        vision_cwd=t["worker"],
        job_worktree=None,
    )
    grok_end = (bound / ".grok" / "config.toml").read_text(encoding="utf-8")
    cur_end = json.loads((t["worker"] / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert "--job-worktree" not in grok_end
    assert "--job-worktree" not in json.dumps(cur_end)
    assert t["harvest"].as_posix() in grok_end.replace("\\", "/")


def test_fr6918_never_writes_user_cursor_mcp(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    launched = _launch_grok_bound(tmp_path)
    t = launched["tree"]
    w = tmp_path / "job-w"
    w.mkdir()
    bw.refresh_live_skill_dag_mcp_files(
        grok_bound_cwd=launched["child"]["cwd"],
        cursor_cwd=t["worker"],
        vision_cwd=t["worker"],
        job_worktree=w,
    )
    assert not (fake_home / ".cursor" / "mcp.json").exists()
    assert not (fake_home / ".grok" / "config.toml").exists()
