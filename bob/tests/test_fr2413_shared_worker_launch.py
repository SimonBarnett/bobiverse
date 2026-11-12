"""FR #2413: tray vs CLI/remote share one launch describe (env, cwd, argv, skills)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_worker_exe_launch_tray_equals_cli(tmp_path):
    root = tmp_path / "bob"
    (root / "worker").mkdir(parents=True)
    (root / "plan").mkdir(parents=True)
    (root / "worker" / "bob-worker.exe").write_bytes(b"MZ")
    local = tmp_path / "localapp"
    local.mkdir()
    tray = bw.describe_worker_exe_launch(
        str(root), "agent", "win-mpre8vi4u6u", local_app_data=str(local), source="tray"
    )
    cli = bw.describe_worker_exe_launch(
        str(root), "agent", "win-mpre8vi4u6u", local_app_data=str(local), source="cli"
    )
    assert tray == cli
    assert tray["argv"][:4] == ["--mode", "agent", "--install-root", str(root)]
    assert "--machine-id" in tray["argv"]
    assert tray["cwd"] == str(root / "worker")
    assert tray["run_exe"].endswith("bob-worker-") or "bob-worker-" in Path(tray["run_exe"]).name
    plan = bw.describe_worker_exe_launch(
        str(root), "plan", "win-mpre8vi4u6u", local_app_data=str(local), source="cli"
    )
    assert plan["cwd"] == str(root / "plan")
    assert plan["argv"][1] == "plan"


def test_agent_child_launch_includes_seat_env_and_skills(tmp_path):
    cwd = tmp_path / "worker"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    (cwd / "AGENTS.md").write_text("x", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(cwd),
        run_dir=run_dir,
        machine="win-mpre8vi4u6u",
        nick="win-mpre8vi4u6u-1",
        agent_exe=r"C:\fake\agent.exe",
    )
    env = child["env"]
    assert env["BOB_OUTBOX"] == str(run_dir / "outbox.txt")
    assert env["BOB_SHOP"] == "#win-mpre8vi4u6u"
    assert env["BOB_NICK"] == "win-mpre8vi4u6u-1"
    assert env["BOB_AGENT_NICK"] == "win-mpre8vi4u6u-1"
    assert env["BOB_MACHINE"] == "win-mpre8vi4u6u"
    # FR #6891: grok agent seats launch from run_dir/bound-cwd (catalog bound).
    assert child["cwd"] == str(run_dir / "bound-cwd")
    assert child["skills_dir"] == str(Path(child["cwd"]) / ".grok" / "skills")
    assert child["env"].get("GROK_HOME") == str(run_dir / "grok-home")
    assert "AGENTS.md" in child["prompt"] or "bobiverse-worker-seat" in child["prompt"]
    assert child["argv"][0] == r"C:\fake\agent.exe"
    assert "--cwd" in child["argv"]
    assert str(run_dir / "bound-cwd") in child["argv"]


def test_plan_child_launch_matches_agent_env_keys(tmp_path):
    """Plan must get the same BOB_* seat env keys as agent (FR #2413)."""
    cwd = tmp_path / "plan"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    worker = tmp_path / "worker"
    worker.mkdir(exist_ok=True)
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "common" / "scripts").mkdir(parents=True)
    (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").write_text("#\n", encoding="utf-8")
    run_dir = tmp_path / "run" / "plan-x"
    run_dir.mkdir(parents=True)
    agent = bw.describe_agent_child_launch(
        kind="grok", mode="agent", cwd=str(worker), run_dir=run_dir,
        machine="m", nick="m-1", agent_exe=r"C:\a.exe",
    )
    run2 = tmp_path / "run" / "plan-y"
    run2.mkdir()
    plan = bw.describe_agent_child_launch(
        kind="grok", mode="plan", cwd=str(cwd), run_dir=run2,
        machine="m", nick="m-plan", agent_exe=r"C:\a.exe",
    )
    bob_keys = {k for k in agent["env"] if k.startswith("BOB_")}
    assert bob_keys == {k for k in plan["env"] if k.startswith("BOB_")}
    for k in ("BOB_OUTBOX", "BOB_SHOP", "BOB_NICK", "BOB_AGENT_NICK", "BOB_MACHINE"):
        assert k in plan["env"]
    # FR #6891: grok agent seats add GROK_HOME for catalog bound; plan does not.
    assert "GROK_HOME" in agent["env"]
    assert "GROK_HOME" not in plan["env"]
