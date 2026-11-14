"""FR #7196: job/tool text must not look like OpenCode model-unavailable."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


PERM = (
    "! permission requested: external_directory "
    r"(C:\ai\bob\worker\.grok\skills\bobiverse-bob-job-fr\*); auto-rejecting`n"
    r'Get-Content -LiteralPath "C:\ai\bob\worker\.grok\skills\bobiverse-bob-job-fr\SKILL.md" failed. '
    "Error: The user rejected permission to use this specific tool call."
)


def test_permission_reject_is_not_model_unavailable():
    assert bw.format_opencode_model_unavailable_error(PERM, model="opencode/deepseek-v4.1-flash-free") is None


def test_job_docs_mentioning_unavailable_is_not_a_probe_hit():
    text = (
        "FROM jeeves #flamingo flamingo-1: FR SimonBarnett/bobiverse#7189 url\n"
        "skill says OpenCode model unavailable if region is wrong\n"
    )
    assert bw.format_opencode_model_unavailable_error(text, model="opencode/deepseek-v4.1-flash-free") is None


def test_provider_region_error_still_reports():
    msg = bw.format_opencode_model_unavailable_error(
        "Error: model not available in your region",
        model="opencode/deepseek-v4.1-flash-free",
    )
    assert msg is not None
    assert "opencode/deepseek-v4.1-flash-free" in msg
    assert "No substitute" in msg


def test_opencode_json_allows_read_only_skill_roots(tmp_path: Path):
    worker = tmp_path / "worker"
    skills = worker / ".grok" / "skills" / "bobiverse-bob-job-fr"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("# fr\n", encoding="utf-8")
    cfg = bw.write_opencode_skill_dag_mcp_config(worker, worker_cwd=str(worker))
    data = __import__("json").loads(cfg.read_text(encoding="utf-8"))
    allow = data.get("permission", {}).get("external_directory", {})
    skill_root = str((worker / ".grok" / "skills").resolve())
    assert allow.get(skill_root) == "allow"
    assert str(worker.resolve()) not in allow
    assert data.get("permission", {}).get("edit", {}).get(skill_root) in (None, "deny", "ask")


def test_probe_unavailable_blocks_ready_line():
    line = bw.opencode_needs_model_line(
        "opencode/deepseek-v4.1-flash-free",
        "not available in your region",
    )
    assert line.startswith("needs model:")
    assert "opencode/deepseek-v4.1-flash-free" in line
    assert "unavailable" in line
    assert "worker ready" not in line
