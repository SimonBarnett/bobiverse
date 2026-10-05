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
    assert env["BOB_MACHINE"] == "win-mpre8vi4u6u"
    assert child["cwd"] == str(cwd)
    assert str(cwd / ".grok" / "skills") in child["skills_dir"] or child["skills_dir"] == str(cwd / ".grok" / "skills")
    assert "AGENTS.md" in child["prompt"] or "bobiverse-worker-seat" in child["prompt"]
    assert child["argv"][0] == r"C:\fake\agent.exe"
    assert "--cwd" in child["argv"] or any(str(cwd) == a for a in child["argv"])


def test_plan_child_launch_matches_agent_env_keys(tmp_path):
    """Plan must get the same BOB_* seat env keys as agent (FR #2413)."""
    cwd = tmp_path / "plan"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    run_dir = tmp_path / "run" / "plan-x"
    run_dir.mkdir(parents=True)
    agent = bw.describe_agent_child_launch(
        kind="grok", mode="agent", cwd=str(tmp_path / "worker"), run_dir=run_dir,
        machine="m", nick="m-1", agent_exe=r"C:\a.exe",
    )
    # use same run_dir shape for plan
    run2 = tmp_path / "run" / "plan-y"
    run2.mkdir()
    (tmp_path / "worker").mkdir(exist_ok=True)
    plan = bw.describe_agent_child_launch(
        kind="grok", mode="plan", cwd=str(cwd), run_dir=run2,
        machine="m", nick="m-plan", agent_exe=r"C:\a.exe",
    )
    assert set(agent["env"]) == set(plan["env"])
    for k in ("BOB_OUTBOX", "BOB_SHOP", "BOB_NICK", "BOB_MACHINE"):
        assert k in plan["env"]
