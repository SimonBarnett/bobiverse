"""FR #10268: public https://bob.ntsa.uk/mcp has list_catalog + get_skill only."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr10268_worker_prompt_names_list_catalog_not_resolve_tool(tmp_path: Path):
    # Isolate from live install tip (FR #8865); C:\ai\bob\worker would load a stale flat template.
    worker = tmp_path / "worker"
    worker.mkdir()
    text = bw.worker_prompt(str(worker), str(tmp_path / "run"), "redqueen", "redqueen-1")
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


def test_fr10268_stale_resolve_tip_falls_through_to_builtin(tmp_path: Path):
    install = tmp_path / "install"
    scripts = install / "scripts"
    scripts.mkdir(parents=True)
    worker = install / "worker"
    worker.mkdir()
    scripts.joinpath("worker_prompt_template.txt").write_text(
        "stale @@WORKER_DIR@@ @@NICK@@ @@MACHINE@@ call skill-dag MCP resolve then get_skill\n",
        encoding="utf-8",
    )
    text = bw.worker_prompt(str(worker), str(tmp_path / "run"), "redqueen", "redqueen-1")
    assert "list_catalog" in text
    assert "MCP resolve then get_skill" not in text


def test_fr10268_shipped_template_names_list_catalog_not_resolve():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "bob" / "scripts" / "worker_prompt_template.txt").read_text(encoding="utf-8")
    assert "list_catalog" in raw
    assert "get_skill" in raw
    assert "MCP resolve then get_skill" not in raw
    assert "(resolve, then get_skill)" not in raw
