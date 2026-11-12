"""FR #6864 S7: worker prompt lists only the core stub for a 100-node index."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import skill_dag_bound as bound


def _index(n: int = 100) -> list[dict]:
    return [{"id": f"unrelated-skill-{i}", "description": f"noise {i}"} for i in range(n)]


def test_s7_prompt_lists_only_core_stub():
    nodes = _index(100)
    assert len(nodes) >= 100
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "flamingo", "flamingo-1")
    catalog = bound.catalog_prompt_bound(nodes)
    captured = prompt + "\n" + catalog
    assert bound.CORE_STUB_ID in captured
    assert bound.CORE_STUB_LINE in captured
    for node in nodes:
        assert node["id"] not in captured
        assert node["description"] not in captured


def test_bound_env_does_not_set_grok_config_or_user_skills(tmp_path, monkeypatch):
    user_cfg = tmp_path / "user-grok" / "config.toml"
    user_cfg.parent.mkdir()
    user_cfg.write_text("[skills]\nenabled = true\n", encoding="utf-8")
    before = user_cfg.read_bytes()
    monkeypatch.setenv("GROK_HOME", str(user_cfg.parent))
    env = bound.apply_bound_env({"GROK_CONFIG": str(tmp_path / "overlay.toml")})
    assert env.get("BOB_SKILL_DAG_BOUND") == bound.CORE_STUB_ID
    assert "GROK_CONFIG" not in env
    assert user_cfg.read_bytes() == before
    assert "[skills]" in user_cfg.read_text(encoding="utf-8")


def test_agent_child_env_has_bound_and_prompt_stub(tmp_path):
    cwd = tmp_path / "worker"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="agent",
        cwd=str(cwd),
        run_dir=run_dir,
        machine="flamingo",
        nick="flamingo-1",
        agent_exe=r"C:\fake\agent.exe",
    )
    assert child["env"].get("BOB_SKILL_DAG_BOUND") == bound.CORE_STUB_ID
    assert "GROK_CONFIG" not in child["env"]
    assert bound.CORE_STUB_ID in child["prompt"]
    for node in _index(20):
        assert node["id"] not in child["prompt"]
