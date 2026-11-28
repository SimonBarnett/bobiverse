"""FR #10373: block stack-polluted harvest-lesson tips at intake + chair offer."""
from __future__ import annotations

import pytest

import harvest_lesson_tip


def test_fr10373_single_skill_path_ok():
    ok = harvest_lesson_tip.harvest_lesson_paths_ok(
        ["common/.grok/skills/harvest/SKILL.md"]
    )
    assert ok


def test_fr10373_skill_sources_and_catalog_ok():
    ok = harvest_lesson_tip.harvest_lesson_paths_ok(
        [
            "common/.grok/skills/harvest/SKILL.md",
            "docs/skill-sources/harvest/in_test.md",
            "apps/mcp-catalog/catalog/harvest/SKILL.md",
            "apps/mcp-catalog/catalog/harvest/meta.json",
        ]
    )
    assert ok


def test_fr10373_stack_pollution_rejected():
    bad = harvest_lesson_tip.harvest_lesson_paths_ok(
        [
            "common/.grok/skills/harvest/SKILL.md",
            "jeeves/tests/test_fr10106_report_502_transcript_fallback.py",
            "bob/scripts/bob_worker.py",
        ]
    )
    assert not bad


def test_fr10373_assert_lesson_files_raises():
    with pytest.raises(ValueError, match="disallowed"):
        harvest_lesson_tip.assert_lesson_files_allowlist(
            [{"path": "bob/scripts/bob_worker.py", "content": "x"}]
        )


def test_fr10373_chair_row_polluted():
    row = {
        "title": "lesson(harvest): example",
        "labels": ["harvest-lesson", "via-intake"],
        "files": [
            {"filename": "common/.grok/skills/harvest/SKILL.md"},
            {"filename": "common/scripts/gitclaim.py"},
        ],
    }
    assert harvest_lesson_tip.harvest_lesson_row_polluted(row)


def test_fr10373_chair_row_clean_not_polluted():
    row = {
        "title": "lesson(harvest): example",
        "labels": ["harvest-lesson"],
        "changed_files": ["common/.grok/skills/harvest/SKILL.md"],
    }
    assert not harvest_lesson_tip.harvest_lesson_row_polluted(row)


def test_fr10373_mrb_not_offerable_when_polluted():
    import gitclaim

    row = {
        "task": "MRB",
        "title": "lesson(harvest): example",
        "labels": ["harvest-lesson"],
        "changed_files": ["bob/scripts/bob_worker.py"],
        "url": "https://github.com/SimonBarnett/bobiverse/pull/1",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) == "harvest_lesson_stack_polluted"


def test_fr10373_intake_skill_source_path_allowlisted(tmp_path):
    import intake

    filer = intake.FakeGitHubFiler()
    err, norm = intake.validate_payload(
        {
            "kind": "harvest",
            "repo": "SimonBarnett/skills-visionary",
            "title": "Plan seat: file-all opens each backlog draft via intake",
            "body": (
                "what: Operator file-all opens each backlog draft with the intake script.\n"
                "where: skills-visionary plan seat.\n"
            ),
            "source": {"skill_book": "harvest-skills-visionary", "agent": "plan-file-all"},
        }
    )
    assert err is None
    rec = intake.file_submission(tmp_path, norm, filer, intake_id="in_plan10373")
    assert rec["state"] == "filed"