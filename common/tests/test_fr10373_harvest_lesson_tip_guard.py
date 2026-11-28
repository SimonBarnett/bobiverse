"""FR #10373: block stack-polluted harvest-lesson tips at intake + chair offer."""
from __future__ import annotations

import pytest

import harvest_lesson_tip


def test_fr10373_single_skill_path_ok():
    ok = harvest_lesson_tip.harvest_lesson_paths_ok(
        ["common/.grok/skills/harvest/SKILL.md"]
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