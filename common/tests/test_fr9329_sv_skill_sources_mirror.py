# -*- coding: utf-8 -*-
"""FR #9329: SV harvest tips sync catalog meta.json + skill-sources _dag when readable."""
from __future__ import annotations

import json
from pathlib import Path

import intake

SV = "SimonBarnett/skills-visionary"
SKILL = ".grok/skills/harvest-skills-visionary/SKILL.md"
CATALOG = "apps/mcp-catalog/catalog/harvest-skills-visionary/SKILL.md"
META = "apps/mcp-catalog/catalog/harvest-skills-visionary/meta.json"
DAG = "docs/skill-sources/skills-visionary/_dag/dag.json"
DAG_INDEX = "docs/skill-sources/skills-visionary/_dag/dag-index.json"

SKILL_BODY = """---
name: harvest-skills-visionary
description: >
  Promote visionary playbooks into SimonBarnett/skills-visionary.
---

# harvest-skills-visionary

- FR #9329 lesson line
"""


def _sample_dag() -> str:
    dag = {
        "version": 1,
        "built": "2026-01-01",
        "repo": "SimonBarnett/skills-visionary",
        "lessonsRoot": "docs/skill-sources/skills-visionary",
        "nodeCount": 1,
        "edgeCount": 0,
        "defaults": {"maxSkills": 8, "maxBytes": 24000},
        "nodes": [
            {
                "id": "skill:harvest-skills-visionary",
                "type": "catalog-skill",
                "title": "old title",
                "path": CATALOG,
                "topic": "harvest",
                "summary": "old summary",
                "triggers": ["harvest-skills-visionary"],
            }
        ],
        "edges": [],
    }
    return json.dumps(dag, indent=2) + "\n"


def _sample_index() -> str:
    index = {
        "version": 1,
        "built": "2026-01-01",
        "note": "Slim index",
        "nodeCount": 1,
        "defaults": {"maxSkills": 8, "maxBytes": 24000},
        "nodes": [
            {
                "id": "skill:harvest-skills-visionary",
                "type": "catalog-skill",
                "title": "old title",
            }
        ],
    }
    return json.dumps(index, indent=2) + "\n"


def test_fr9329_meta_path_and_content():
    assert intake.mcp_catalog_meta_path(SKILL) == META
    assert intake.mcp_catalog_meta_path("common/.grok/skills/harvest/SKILL.md") is None
    body = intake.mcp_catalog_meta_content(SKILL, SKILL_BODY)
    assert body is not None
    meta = json.loads(body)
    assert meta["name"] == "harvest-skills-visionary"
    assert meta["topic"] == "harvest"
    assert meta["source"] == SKILL
    assert "Promote visionary" in meta["description"]


def test_fr9329_with_mcp_catalog_meta_on_sv():
    files = [{"path": SKILL, "content": SKILL_BODY}]
    out = intake.with_mcp_catalog_mirror(SV, SKILL, files)
    out = intake.with_mcp_catalog_meta(SV, SKILL, out)
    paths = [f["path"] for f in out]
    assert META in paths
    meta = json.loads(next(f["content"] for f in out if f["path"] == META))
    assert meta["name"] == "harvest-skills-visionary"


def test_fr9329_with_mcp_catalog_meta_skips_other_repos():
    files = [{"path": SKILL, "content": SKILL_BODY}]
    out = intake.with_mcp_catalog_meta("SimonBarnett/bobiverse", SKILL, files)
    assert [f["path"] for f in out] == [SKILL]


def test_fr9329_patch_dag_updates_summary():
    patched = intake.patch_sv_skill_sources_dag(
        skill_id="harvest-skills-visionary",
        title="harvest skills visionary",
        description="Promote visionary playbooks into SimonBarnett/skills-visionary.",
        topic="harvest",
        dag_raw=_sample_dag(),
        index_raw=_sample_index(),
        built="2026-11-23",
    )
    assert patched is not None
    dag_body, index_body = patched
    dag = json.loads(dag_body)
    assert dag["built"] == "2026-11-23"
    node = next(n for n in dag["nodes"] if n["id"] == "skill:harvest-skills-visionary")
    assert "Promote visionary" in node["summary"]
    index = json.loads(index_body)
    assert index["built"] == "2026-11-23"


def test_fr9329_skill_sources_omitted_without_filer_dag():
    files = [{"path": SKILL, "content": SKILL_BODY}]
    out = intake.with_sv_skill_sources_dag(SV, SKILL, files, filer=None)
    assert DAG not in [f["path"] for f in out]


def test_fr9329_skill_sources_patched_when_filer_has_dag():
    filer = intake.FakeGitHubFiler()
    filer.repo_files[DAG] = _sample_dag()
    filer.repo_files[DAG_INDEX] = _sample_index()
    files = [{"path": SKILL, "content": SKILL_BODY}]
    out = intake.with_sv_skill_sources_dag(
        SV, SKILL, files, filer=filer, built="2026-11-23"
    )
    paths = [f["path"] for f in out]
    assert DAG in paths and DAG_INDEX in paths
    dag = json.loads(next(f["content"] for f in out if f["path"] == DAG))
    node = next(n for n in dag["nodes"] if n["id"] == "skill:harvest-skills-visionary")
    assert "Promote visionary" in node["summary"]


def test_fr9329_intake_sv_tip_includes_meta_and_dag(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[SKILL] = SKILL_BODY.replace("- FR #9329 lesson line\n", "")
    filer.repo_files[DAG] = _sample_dag()
    filer.repo_files[DAG_INDEX] = _sample_index()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": SV,
            "title": "harvest: skill-sources follow-up",
            "body": (
                "Session summary:\nSV tip skill-sources\n\n"
                "Lessons:\n- FR #9329 intake tips must sync skill-sources dag and meta\n"
            ),
            "source": {
                "skill_book": "harvest-skills-visionary",
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9329_sv")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    paths = [str(f.get("path") or "").replace("\\", "/") for f in (pr.get("files") or [])]
    assert SKILL in paths
    assert CATALOG in paths
    assert META in paths
    assert DAG in paths
    assert DAG_INDEX in paths
    by_path = {
        str(f.get("path") or "").replace("\\", "/"): str(f.get("content") or "")
        for f in (pr.get("files") or [])
    }
    assert by_path[SKILL] == by_path[CATALOG]
    meta = json.loads(by_path[META])
    assert meta["name"] == "harvest-skills-visionary"
    dag = json.loads(by_path[DAG])
    node = next(n for n in dag["nodes"] if n["id"] == "skill:harvest-skills-visionary")
    assert node["summary"]
