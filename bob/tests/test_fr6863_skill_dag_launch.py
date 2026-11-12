"""FR #6863: worker launch uses skill-dag resolve/get_skill; MCP config on worker cwd only."""
from __future__ import annotations

import os
from pathlib import Path

import bob_worker as bw


def test_s5_worker_prompt_names_resolve_and_get_skill():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "flamingo", "flamingo-1")
    assert "resolve" in text
    assert "get_skill" in text
    assert "FIRST read the skills in" not in text


def test_s5_rules_text_agent_names_resolve_and_get_skill():
    text = bw.rules_text(r"C:\ai\bob\worker", "agent")
    assert "resolve" in text
    assert "get_skill" in text
    assert "Read the skills in" not in text


def test_s5_plan_prompt_still_reads_plan_skills():
    text = bw.plan_prompt(r"C:\ai\bob\plan")
    assert "FIRST read the skills in" in text


def test_s6_agent_launch_writes_worker_mcp_not_home_or_plan(tmp_path, monkeypatch):
    home = tmp_path / "home"
    grok_home = home / ".grok"
    grok_home.mkdir(parents=True)
    home_cfg = grok_home / "config.toml"
    home_cfg.write_text("# user grok\n", encoding="utf-8")
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GROK_HOME", str(grok_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    worker = tmp_path / "worker"
    plan = tmp_path / "plan"
    worker.mkdir()
    plan.mkdir()
    run = tmp_path / "run"
    run.mkdir()

    agent_spec = bw.build_launch(
        "grok", "agent", str(worker), "prompt", "grok.exe", run, session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    bw.write_skill_dag_mcp_config_if_agent(agent_spec)

    wcfg = worker / ".grok" / "config.toml"
    assert wcfg.is_file()
    body = wcfg.read_text(encoding="utf-8")
    assert "[mcp_servers" in body
    assert "skill-dag" in body

    plan_spec = bw.build_launch(
        "grok", "plan", str(plan), "prompt", "grok.exe", run, session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    )
    bw.write_skill_dag_mcp_config_if_agent(plan_spec)
    assert not (plan / ".grok" / "config.toml").exists()
    assert home_cfg.read_text(encoding="utf-8") == "# user grok\n"
