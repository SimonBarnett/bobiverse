"""FR #4968: intake lesson PR triage boilerplate must not be lesson-of-lesson.

Webhook path stores the full PR body (template ver=20261020-fr4917 contains
``board CLOSED not-useful``). That must remain offerable. Real meta tips stay filtered.
purge_dead_mrb logs repo/#id + reason.
"""
from __future__ import annotations

import gitclaim

# Real intake body shape (a-search #4960 / ver=20261020-fr4917), secrets omitted.
INTAKE_LESSON_BODY = """\
MRB (light triage): is the lesson useful, generalised, non-duplicate, and a fit for this repo's vision/AGENTS.md? PASS -> merge. Not useful / off-vision -> close with a one-line reason (board CLOSED not-useful). Duplicate -> close citing the existing lesson. Wrong owner -> re-file or MOVED (FR #3299); leave OPEN if the owner repo does not exist yet. Plan content only (requirements, designs, product decisions, FR/issue lists from a Plan seat) -> close 'plan content, not a lesson' (never hold it OPEN); move any how-to-plan lesson inside to SimonBarnett/skills-visionary.

Target skill book: `harvest-agent-skills` (`.grok/skills/harvest-agent-skills/SKILL.md`).

Lessons:
- FR #4943 import-failure MRB: require POST /bob/v1/intake with dedupe_key (not GitHub Issues API alone); assemble secret-shaped test fixtures via fakeSecrets.js (FR #3304); wire tools/dbimport catch paths too

---

Session summary:
MRB #4950 FAIL: GitGuardian FR3304 fixtures (Refs #4958); tip uses GH Issues API but FR #4943 requires bobiverse intake with dedupe_key; folder dbimport unwired

Lessons:
- FR #4943 import-failure MRB: require POST /bob/v1/intake with dedupe_key (not GitHub Issues API alone); assemble secret-shaped test fixtures via fakeSecrets.js (FR #3304); wire tools/dbimport catch paths too

---
_via-intake id=`in_ef5451f6b2df4c94` ts=`2026-10-25T13:22:33Z`_
_source machine=`win-mpre8vi4u6u` agent=`Invoke-BobiverseHarvest` book=`harvest-agent-skills` ver=`20261020-fr4917` seat=`win-mpre8vi4u6u-20172`_
"""


def test_fr4968_strip_removes_closed_not_useful_instruction():
    stripped = gitclaim.strip_intake_light_triage_boilerplate(INTAKE_LESSON_BODY)
    assert "board CLOSED not-useful" not in stripped
    assert "require POST /bob/v1/intake" in stripped
    assert "Target skill book" in stripped


def test_fr4968_intake_template_body_is_not_lesson_of_lesson():
    assert not gitclaim.is_lesson_of_lesson_pr(
        title="lesson(harvest-agent-skills): FR #4943 import-failure MRB: require POST /bob/v1/intake with dedupe_key...",
        body=INTAKE_LESSON_BODY,
        labels=("harvest-lesson", "via-intake"),
        head_ref="intake/in_ef5451f6b2df4c94",
    )


def test_fr4968_intake_template_row_is_offerable():
    row = {
        "task": "MRB",
        "repo": "SimonBarnett/a-search",
        "id": "#4960",
        "title": "lesson(harvest-agent-skills): FR #4943 import-failure MRB",
        "body": INTAKE_LESSON_BODY,
        "labels": ["harvest-lesson", "via-intake"],
        "head_ref": "intake/in_ef5451f6b2df4c94",
        "url": "https://github.com/SimonBarnett/a-search/pull/4960",
    }
    assert gitclaim.mrb_row_not_offerable_reason(row) is None
    assert gitclaim.mrb_row_offerable(row) is True


def test_fr4968_real_lesson_of_lesson_still_filtered():
    assert gitclaim.is_lesson_of_lesson_pr(
        title="lesson(harvest-agent-skills): Harvest tip restating mrb4661",
        body="CLOSED-duplicate; DONE PASS\nRefs SimonBarnett/a-search#4683",
        labels=("harvest-lesson",),
        head_ref="intake/in_x",
    )
    assert gitclaim.is_lesson_of_lesson_pr(
        title="lesson(harvest-agent-skills): tip-loop meta",
        body="MRB CLOSED not-useful: one-box anecdote; FAIL-supersede citing #4769",
        labels=("harvest-lesson",),
        head_ref="intake/in_y",
    )


def test_fr4968_purge_dead_mrb_logs_repo_pr_and_reason():
    doc = {
        "unaccepted": [
            {
                "task": "MRB",
                "repo": "SimonBarnett/a-search",
                "id": "#4999",
                "title": "lesson(harvest-agent-skills): tip-loop meta twin",
                "body": "FAIL-supersede; tip-loop; CLOSED-duplicate of #4769",
                "labels": ["harvest-lesson"],
                "head_ref": "intake/in_meta",
                "url": "https://github.com/SimonBarnett/a-search/pull/4999",
            }
        ],
        "accepted": [],
        "done": [],
    }
    lines: list[str] = []
    n = gitclaim._purge_dead_mrb_unaccepted(doc, log=lines.append)
    assert n == 1
    assert doc["unaccepted"] == []
    assert any(
        "purge_dead_mrb" in ln
        and "SimonBarnett/a-search#4999" in ln
        and "lesson_of_lesson" in ln
        for ln in lines
    )
