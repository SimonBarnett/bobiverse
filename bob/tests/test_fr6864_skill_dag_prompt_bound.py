"""FR #6864 / #6891 S7: harness skill catalog bound (core stub only)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import bob_worker as bw
import skill_dag_bound as bound


def _index(n: int = 100) -> list[dict]:
    return [{"id": f"unrelated-skill-{i}", "description": f"noise {i}"} for i in range(n)]


def test_prompt_fragment_never_interpolates_index_nodes():
    """Index text must not appear in the prompt fragment (necessary, not sufficient for S7)."""
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


def test_prepare_bound_cwd_only_core_skill_and_mcp_absolute(tmp_path):
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills" / "bobiverse-bob").mkdir(parents=True)
    (worker / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md").write_text(
        "---\nname: bobiverse-bob\ndescription: must not be harness-listed from bound cwd\n---\n",
        encoding="utf-8",
    )
    (worker / "AGENTS.md").write_text("agents", encoding="utf-8")
    install = tmp_path
    (install / "common" / "scripts").mkdir(parents=True)
    mcp = install / "common" / "scripts" / "skill_dag_mcp.py"
    mcp.write_text("# stub\n", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    b = bound.prepare_bound_agent_cwd(run_dir, worker, mcp_script=mcp)
    assert b == run_dir / bound.BOUND_CWD_NAME
    core = b / ".grok" / "skills" / bound.CORE_STUB_ID / "SKILL.md"
    assert core.is_file()
    skill_dirs = [p.name for p in (b / ".grok" / "skills").iterdir() if p.is_dir()]
    assert skill_dirs == [bound.CORE_STUB_ID]
    cfg = (b / ".grok" / "config.toml").read_text(encoding="utf-8")
    assert "skill-dag" in cfg
    assert mcp.as_posix() in cfg
    assert (worker / ".grok" / "skills").resolve().as_posix() in cfg
    # Fat install skills stay on disk for MCP roots; bound cwd does not copy them in.
    assert (worker / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md").is_file()


def test_prepare_seat_grok_home_does_not_touch_user_config(tmp_path):
    user = tmp_path / "user-grok"
    user.mkdir()
    (user / "auth.json").write_text("{}", encoding="utf-8")
    (user / "config.toml").write_text("[skills]\npaths = [\"X\"]\n", encoding="utf-8")
    before = (user / "config.toml").read_bytes()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    trust = tmp_path / "bound"
    trust.mkdir()
    home = bound.prepare_seat_grok_home(run_dir, trust_paths=[trust], user_grok_home=user)
    assert home == run_dir / bound.GROK_HOME_NAME
    assert not (home / "auth.json").exists()
    assert (user / "config.toml").read_bytes() == before
    seat_cfg = (home / "config.toml").read_text(encoding="utf-8")
    assert "paths = []" in seat_cfg
    assert str(trust) in (home / "trusted_folders.toml").read_text(encoding="utf-8")


def test_agent_child_launch_grok_uses_bound_cwd_and_grok_home(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / ".grok" / "skills" / "noise").mkdir(parents=True)
    (worker / ".grok" / "skills" / "noise" / "SKILL.md").write_text(
        "---\nname: noise\ndescription: noise\n---\n", encoding="utf-8"
    )
    (worker / "AGENTS.md").write_text("x", encoding="utf-8")
    (tmp_path / "common" / "scripts").mkdir(parents=True)
    (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").write_text("#\n", encoding="utf-8")
    run_dir = tmp_path / "run" / "worker-x"
    run_dir.mkdir(parents=True)
    # Fake user grok home so prepare can copy auth without touching the real one.
    user = tmp_path / "fake-user-grok"
    user.mkdir()
    (user / "auth.json").write_text("{}", encoding="utf-8")
    old = os.environ.get("GROK_HOME")
    os.environ["GROK_HOME"] = str(user)
    try:
        child = bw.describe_agent_child_launch(
            kind="grok",
            mode="agent",
            cwd=str(worker),
            run_dir=run_dir,
            machine="flamingo",
            nick="flamingo-1",
            agent_exe=r"C:\fake\agent.exe",
        )
    finally:
        if old is None:
            os.environ.pop("GROK_HOME", None)
        else:
            os.environ["GROK_HOME"] = old
    assert child["cwd"] == str(run_dir / bound.BOUND_CWD_NAME)
    assert child["env"].get("BOB_SKILL_DAG_BOUND") == bound.CORE_STUB_ID
    assert child["env"].get("GROK_HOME") == str(run_dir / bound.GROK_HOME_NAME)
    assert "GROK_CONFIG" not in child["env"]
    assert bound.CORE_STUB_ID in child["prompt"]
    assert (Path(child["cwd"]) / ".grok" / "skills" / bound.CORE_STUB_ID / "SKILL.md").is_file()
    for node in _index(20):
        assert node["id"] not in child["prompt"]


def test_plan_child_launch_keeps_caller_cwd(tmp_path):
    cwd = tmp_path / "plan"
    cwd.mkdir()
    (cwd / ".grok" / "skills").mkdir(parents=True)
    run_dir = tmp_path / "run" / "plan-x"
    run_dir.mkdir(parents=True)
    child = bw.describe_agent_child_launch(
        kind="grok",
        mode="plan",
        cwd=str(cwd),
        run_dir=run_dir,
        machine="flamingo",
        nick="flamingo-plan",
        agent_exe=r"C:\fake\agent.exe",
    )
    assert child["cwd"] == str(cwd)


@pytest.mark.skipif(bound.find_agent_exe() is None, reason="grok agent.exe not installed")
def test_s7_grok_inspect_bound_cwd_lists_only_core_stub(tmp_path):
    """S7 measurement: grok inspect on the bound seat cwd (outside install tree)."""
    worker = tmp_path / "worker"
    (worker / ".grok" / "skills" / "bobiverse-bob").mkdir(parents=True)
    (worker / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md").write_text(
        "---\nname: bobiverse-bob\ndescription: unrelated fixture must not appear\n---\n",
        encoding="utf-8",
    )
    (worker / "AGENTS.md").write_text("agents", encoding="utf-8")
    (tmp_path / "common" / "scripts").mkdir(parents=True)
    (tmp_path / "common" / "scripts" / "skill_dag_mcp.py").write_text("#\n", encoding="utf-8")
    # 100-node index outside .grok/skills (MCP roots may read these; harness must not).
    idx = tmp_path / "index-fixture"
    for i in range(100):
        d = idx / f"unrelated-skill-{i}"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: unrelated-skill-{i}\ndescription: noise {i}\n---\n",
            encoding="utf-8",
        )
    run_dir = tmp_path / "run" / "seat"
    run_dir.mkdir(parents=True)
    user = tmp_path / "user-grok"
    user.mkdir()
    real_auth = Path.home() / ".grok" / "auth.json"
    if real_auth.is_file():
        user.joinpath("auth.json").write_bytes(real_auth.read_bytes())
    else:
        user.joinpath("auth.json").write_text("{}", encoding="utf-8")
    bundled = Path.home() / ".grok" / "bundled" / "skills"
    if bundled.is_dir():
        # Point seat home at a copy that still sees real bundled via config path.
        pass
    b = bound.prepare_bound_agent_cwd(
        run_dir,
        worker,
        mcp_script=tmp_path / "common" / "scripts" / "skill_dag_mcp.py",
        mcp_roots=[worker / ".grok" / "skills", idx],
    )
    home = bound.prepare_seat_grok_home(run_dir, trust_paths=[b], user_grok_home=user)
    skills = bound.capture_inspect_skills(b, grok_home=home)
    names = {s.get("name") for s in skills}
    for i in range(100):
        assert f"unrelated-skill-{i}" not in names
    assert "bobiverse-bob" not in names
    bound.assert_s7_catalog_bound(skills)
