"""FR #10268: public https://bob.ntsa.uk/mcp has list_catalog + get_skill only."""
from __future__ import annotations

import bob_worker as bw


def test_fr10268_worker_prompt_names_list_catalog_not_resolve_tool():
    text = bw.worker_prompt(r"C:\ai\bob\worker", r"C:\run", "redqueen", "redqueen-1")
    assert "list_catalog" in text
    assert "get_skill" in text
    assert "(resolve, then get_skill)" not in text
    assert "MCP resolve then get_skill" not in text


def test_fr10268_rules_text_names_list_catalog_not_resolve_tool():
    text = bw.rules_text(r"C:\ai\bob\worker", "agent")
    assert "list_catalog" in text
    assert "get_skill" in text
    assert "no resolve tool" in text
    assert "(resolve, then get_skill)" not in text


def test_fr10268_opencode_finish_prompt_no_resolve_tool():
    text = bw.opencode_job_finish_steps(
        job_key="FR SimonBarnett/bobiverse#10268",
        worktree=r"C:\wt",
        outbox=r"C:\ob",
    )
    assert "MCP resolve then get_skill" not in text
    assert "get_skill" in text