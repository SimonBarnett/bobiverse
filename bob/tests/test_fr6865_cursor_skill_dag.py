"""FR #6865: Cursor worker seat writes project .cursor/mcp.json only; no user catalog drop."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw


def test_cursor_mcp_path_is_workspace_mcp_json():
    assert bw.CURSOR_SKILL_DAG_MCP_RELPATH.replace("\\", "/") == ".cursor/mcp.json"


def test_cursor_no_process_local_catalog_drop():
    assert bw.cursor_skill_catalog_process_local_drop() is None


def test_cursor_launch_files_include_mcp_and_resolve(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    prompt = bw.worker_prompt(str(worker), str(run), "flamingo", "flamingo-1")
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(worker),
        prompt,
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    mcp_path = str(worker / ".cursor" / "mcp.json")
    assert mcp_path in spec.files
    body = spec.files[mcp_path]
    data = json.loads(body)
    assert "skill-dag" in data.get("mcpServers", {})
    assert "resolve" in spec.files[str(run / "prompt.txt")]
    assert "get_skill" in spec.files[str(run / "prompt.txt")]
    assert spec.write_cursor_skill_dag_mcp is True


def test_cursor_launch_leaves_user_mcp_unchanged(tmp_path, monkeypatch):
    home = tmp_path / "home"
    cursor_home = home / ".cursor"
    cursor_home.mkdir(parents=True)
    user_mcp = cursor_home / "mcp.json"
    user_mcp.write_text('{"mcpServers":{"keep":{"command":"true"}}}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))

    worker = tmp_path / "worker"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "cursor",
        "agent",
        str(worker),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    bw.write_cursor_skill_dag_mcp_config_if_agent(spec)
    written = worker / ".cursor" / "mcp.json"
    assert written.is_file()
    data = json.loads(written.read_text(encoding="utf-8"))
    assert "skill-dag" in data["mcpServers"]
    assert user_mcp.read_text(encoding="utf-8") == '{"mcpServers":{"keep":{"command":"true"}}}\n'


def test_plan_cursor_does_not_write_mcp(tmp_path):
    worker = tmp_path / "plan"
    worker.mkdir()
    run = tmp_path / "run"
    run.mkdir()
    spec = bw.build_launch(
        "cursor",
        "plan",
        str(worker),
        "prompt",
        r"C:\fake\agent.cmd",
        run,
        session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    assert spec.write_cursor_skill_dag_mcp is False
    assert not any(p.replace("\\", "/").endswith(".cursor/mcp.json") for p in spec.files)
    bw.write_cursor_skill_dag_mcp_config_if_agent(spec)
    assert not (worker / ".cursor" / "mcp.json").exists()
