"""FR #9303: skills-visionary harvest tips must include mcp-catalog SKILL.md mirror.

Intake opens tips via GitHub file blobs (no tip worktree), so it cannot run
``tools/build-skill-dag.py``. Mirror the same SKILL.md content under
``apps/mcp-catalog/catalog/<book>/SKILL.md`` in the tip files[] (SV #198 / FR #182).
"""
from __future__ import annotations

from pathlib import Path

import intake

SV = "SimonBarnett/skills-visionary"
SKILL = ".grok/skills/harvest-skills-visionary/SKILL.md"
CATALOG = "apps/mcp-catalog/catalog/harvest-skills-visionary/SKILL.md"


def test_fr9303_mcp_catalog_mirror_path_helper():
    assert intake.mcp_catalog_mirror_path(SKILL) == CATALOG
    assert intake.mcp_catalog_mirror_path("bob/.grok/skills/harvest/SKILL.md") is None
    assert intake.mcp_catalog_mirror_path("common/.grok/skills/harvest/SKILL.md") is None
    assert intake.mcp_catalog_mirror_path("docs/skill-sources/x.md") is None


def test_fr9303_with_mcp_catalog_mirror_skills_visionary():
    files = [{"path": SKILL, "content": "# harvest-skills-visionary\n\n- lesson\n"}]
    out = intake.with_mcp_catalog_mirror(SV, SKILL, files)
    paths = [f["path"] for f in out]
    assert SKILL in paths
    assert CATALOG in paths
    catalog = next(f for f in out if f["path"] == CATALOG)
    assert catalog["content"] == files[0]["content"]


def test_fr9303_with_mcp_catalog_mirror_skips_other_repos():
    files = [{"path": SKILL, "content": "# x\n"}]
    out = intake.with_mcp_catalog_mirror("SimonBarnett/bobiverse", SKILL, files)
    assert [f["path"] for f in out] == [SKILL]
    out2 = intake.with_mcp_catalog_mirror("SimonBarnett/a-search", SKILL, files)
    assert [f["path"] for f in out2] == [SKILL]


def test_fr9303_intake_skills_visionary_tip_includes_catalog(tmp_path: Path):
    filer = intake.FakeGitHubFiler()
    filer.repo_files[SKILL] = "# harvest-skills-visionary\n\n"
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": SV,
            "title": "harvest: catalog mirror for intake tips",
            "body": (
                "Session summary:\nSV tip catalog\n\n"
                "Lessons:\n- FR #9303 intake tips must sync mcp-catalog mirror\n"
            ),
            "source": {
                "skill_book": "harvest-skills-visionary",
                "agent": "Invoke-BobiverseHarvest",
            },
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_fr9303_sv")
    assert rec["state"] == "filed"
    pr = filer.prs[-1]
    assert pr["repo"] == SV
    paths = [str(f.get("path") or "").replace("\\", "/") for f in (pr.get("files") or [])]
    assert SKILL in paths
    assert CATALOG in paths
    by_path = {
        str(f.get("path") or "").replace("\\", "/"): str(f.get("content") or "")
        for f in (pr.get("files") or [])
    }
    assert by_path[SKILL] == by_path[CATALOG]
    assert "FR #9303" in by_path[SKILL] or "mcp-catalog" in by_path[SKILL]


def test_fr9303_merge_then_mirror_idempotent():
    """Calling with_mcp_catalog_mirror twice must not duplicate the catalog path."""
    files = intake.merge_lesson_pr_files(SKILL, "# book\n\n- a\n", None)
    once = intake.with_mcp_catalog_mirror(SV, SKILL, files)
    twice = intake.with_mcp_catalog_mirror(SV, SKILL, once)
    assert [f["path"] for f in once].count(CATALOG) == 1
    assert [f["path"] for f in twice].count(CATALOG) == 1
