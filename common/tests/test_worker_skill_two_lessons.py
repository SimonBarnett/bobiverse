"""bobiverse-bob-worker get_skill stays under OpenCode's 50 KiB tool cap.

OpenCode Truncate.MAX_BYTES is 50 KiB. A larger get_skill result is spilled
and the seat is told not to read the file. Intake bullets live in lessons.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "common" / "scripts"))

import bob_skill_catalog as catalog  # noqa: E402
import intake  # noqa: E402

SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
LESSONS = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-worker" / "lessons.md"
CAP = 50 * 1024


def test_worker_skill_get_skill_under_opencode_tool_cap():
    rec = catalog.skill_record(SKILL)
    blob = json.dumps(
        {
            "name": rec["name"],
            "title": rec["title"],
            "description": rec["description"],
            "skillMd": rec["skillMd"],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    assert len(blob) <= CAP
    assert "lessons.md" in rec["skillMd"]
    assert "## Harvested lessons (intake)" not in rec["skillMd"]
    assert "## Start it (three ways)" in rec["skillMd"]


def test_worker_intake_archive_kept():
    text = LESSONS.read_text(encoding="utf-8")
    assert "## Harvested lessons (intake)" in text
    assert "bob-worker-net embeds SourceCommit" in text
    assert "<!-- harvest-lessons-eof -->" in text


def test_worker_new_bullets_append_to_lessons():
    assert (
        intake.lesson_append_path("bob/.grok/skills/bobiverse-bob-worker/SKILL.md")
        == intake.WORKER_LESSONS_ARCHIVE
    )
