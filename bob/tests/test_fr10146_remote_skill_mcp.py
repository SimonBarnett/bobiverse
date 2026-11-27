"""FR #10146: worker seats use https://bob.ntsa.uk/mcp, not a local skill-dag process."""
from __future__ import annotations

import bob_worker as bw


def test_fr10146_seat_configs_are_remote_url(tmp_path):
    worker = tmp_path / "worker"
    worker.mkdir()
    grok = bw.write_skill_dag_mcp_config(str(worker))
    body = grok.read_text(encoding="utf-8")
    assert f'url = "{bw.BOB_SKILL_MCP_URL}"' in body
    assert "command" not in body
    cur = bw.cursor_skill_dag_mcp_document(str(worker))["mcpServers"]["skill-dag"]
    assert cur == {"url": bw.BOB_SKILL_MCP_URL}
    oc = bw.opencode_skill_dag_mcp_document(str(worker))["mcp"]["skill-dag"]
    assert oc["type"] == "remote"
    assert oc["url"] == bw.BOB_SKILL_MCP_URL
    assert "command" not in oc


def test_fr10146_between_jobs_does_not_git_overlay(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("git skill overlay must not run")

    monkeypatch.setattr(
        "sync_install_skills.sync_install_skills_from_origin",
        boom,
        raising=False,
    )
    out = bw.maybe_sync_install_skills(install_root=r"C:\ai\bob", job_busy=False)
    assert out["reason"] == "remote-mcp"
    assert out["ok"] is True
