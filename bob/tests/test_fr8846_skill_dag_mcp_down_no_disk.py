"""FR #8846: skill-dag MCP down must not silently fall back to disk skills."""
from __future__ import annotations

import json
from pathlib import Path

import bob_worker as bw
import gitclaim


def test_fr8846_worker_prompt_forbids_disk_fallback_and_names_giveup():
    prompt = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\ai\bob\home", "marchhare", "marchhare-1")
    assert "FR #8846" in prompt
    assert "skill-dag-mcp-down" in prompt
    assert "GIVEUP" in prompt
    low = prompt.lower()
    assert "grepping job skills from disk" in low or "from disk" in low
    assert "never" in low
    # FR #8785 path: mcp.json only, never invent bob\\bob\\scripts
    assert ".cursor/mcp.json" in prompt or ".cursor\\mcp.json" in prompt
    assert "bob\\bob\\scripts" not in prompt
    assert "bob/bob/scripts" not in prompt
    assert r"C:\ai\bob\bob\scripts\skill_dag_mcp.py" not in prompt
    assert "`--root` / `--job-worktree` args" not in prompt
    assert "--job-worktree-file" in prompt


def test_fr8846_rules_text_forbids_disk_continue():
    rules = bw.rules_text(r"C:\ai\bob\worker", "agent")
    assert "skill-dag-mcp-down" in rules
    assert "from disk" in rules.lower()
    assert "GIVEUP" in rules


def test_fr8846_cursor_launch_writes_skill_dag_mcp_server(tmp_path):
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
    mcp_key = str(worker / ".cursor" / "mcp.json")
    assert mcp_key in spec.files
    data = json.loads(spec.files[mcp_key])
    assert "skill-dag" in data.get("mcpServers", {})
    server = data["mcpServers"]["skill-dag"]
    assert server.get("url") == bw.BOB_SKILL_MCP_URL
    assert "command" not in server
    prompt_txt = spec.files[str(run / "prompt.txt")]
    assert "skill-dag-mcp-down" in prompt_txt
    assert "bob\\bob\\scripts" not in prompt_txt


def test_fr8846_skill_dag_mcp_down_is_seat_fault_reason():
    assert gitclaim.is_skill_dag_down_reason("skill-dag-mcp-down") is True
    assert gitclaim.is_skill_dag_down_reason("skill_dag_mcp_down") is True
    assert gitclaim.is_skill_dag_down_reason("skill-dag-mcp-down:cli-failed") is True
    assert gitclaim.is_skill_dag_down_reason("skill-dag-down:exit-1") is True
    assert gitclaim.is_skill_dag_down_reason("out-of-fuel") is False


def test_fr8846_disk_fallback_narrative_is_not_success_path():
    """Prompt must not present disk reads as an OK alternative to MCP/CLI."""
    prompt = bw.worker_prompt(r"D:\ai\bob\worker", r"D:\run", "marchhare", "marchhare-9")
    # Forbidden success narrative (exact class of the seat utterance that filed this FR).
    assert "MCP is down; reading" not in prompt
    assert "reading FR/IRC skills from disk" not in prompt.lower()
    assert "skill-dag-mcp-down" in prompt
