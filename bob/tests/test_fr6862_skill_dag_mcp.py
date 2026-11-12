"""FR #6862: stdio skill-dag MCP resolve / get_skill / status."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import skill_dag_mcp as mcp

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "skill-dag"


@pytest.fixture
def server(tmp_path: Path):
    fat = tmp_path / "fat"
    fat.mkdir()
    body = "x" * 8000
    (fat / "SKILL.md").write_text(
        "---\nname: fat-skill\ndescription: oversized body\ndepends_on: []\n---\n\n" + body,
        encoding="utf-8",
    )
    roots = [FIXTURES, tmp_path]
    return mcp.SkillDagServer(roots=roots, max_bytes=4000)


def test_s2_fr_resolve_includes_job_irc_excludes_uat(server):
    out = server.resolve("FR")
    ids = [n["id"] for n in out["matched"]]
    assert "bobiverse-bob-job-fr" in ids
    assert "bobiverse-bob-job-irc" in ids
    assert "bobiverse-bob-job-uat" not in ids
    skipped_ids = [s["id"] for s in out.get("skipped") or []]
    assert "bobiverse-bob-job-uat" not in skipped_ids


def test_s4_fat_body_skipped_response_within_cap(server):
    out = server.resolve("fat-skill")
    skipped_ids = [s["id"] for s in out.get("skipped") or []]
    assert "fat-skill" in skipped_ids
    blob = json.dumps(out, ensure_ascii=False)
    assert len(blob.encode("utf-8")) <= server.max_bytes


def test_get_skill_refuses_path_outside_roots(server):
    result = server.get_skill(str(Path(__file__).resolve()))
    assert result.get("ok") is False
    assert result.get("reason") == "path_refused"


def test_get_skill_returns_one_body_under_root(server):
    path = FIXTURES / "job-irc" / "SKILL.md"
    result = server.get_skill(str(path))
    assert result.get("ok") is True
    assert "job-irc" in result.get("body", "")
    assert "job-fr fixture" not in result.get("body", "")


def test_status_has_index_time_and_node_count(server):
    st = server.status()
    assert st["node_count"] >= 3
    assert st.get("index_time")
    assert "last_error" in st


def test_tools_list_has_no_list_all(server):
    names = {t["name"] for t in server.tools_list()}
    assert names == {"resolve", "get_skill", "status"}
    assert "list" not in names
    assert "list_all" not in names


def test_stdio_has_no_bind(server):
    src = Path(mcp.__file__).read_text(encoding="utf-8")
    assert "listen(" not in src
    assert "bind(" not in src
    assert "HTTPServer" not in src
