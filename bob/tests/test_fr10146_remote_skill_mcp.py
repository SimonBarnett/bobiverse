"""FR #10146: worker seats use https://bob.ntsa.uk/mcp, not a local skill-dag process."""
from __future__ import annotations

from pathlib import Path

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


def test_fr10146_cursor_mcp_is_on_git_root_and_approved():
    import json
    import shutil
    import subprocess

    repo = Path(r"C:\cmr")
    home = Path(r"C:\cmh")
    shutil.rmtree(repo, ignore_errors=True)
    shutil.rmtree(home, ignore_errors=True)
    worker = repo / "worker"
    worker.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    try:
        cfg = bw.write_cursor_skill_dag_mcp_config(str(worker), home=home)
        assert cfg == repo / ".cursor" / "mcp.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        server = data["mcpServers"]["skill-dag"]
        assert server["url"] == bw.BOB_SKILL_MCP_URL
        seat = json.loads((worker / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        assert seat["mcpServers"]["skill-dag"]["url"] == bw.BOB_SKILL_MCP_URL
        root = bw.cursor_git_project_root(worker)
        ident = bw.cursor_mcp_approval_id(root, server)
        approvals = json.loads(
            (home / ".cursor" / "projects" / bw.cursor_project_slug(root) / "mcp-approvals.json").read_text(
                encoding="utf-8"
            )
        )
        assert ident in approvals
    finally:
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


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
