"""FR #8310: harvest lessons.md archive still dedupes on-main tips."""
from __future__ import annotations

import intake


class _Filer:
    def __init__(self, files: dict[str, str]):
        self._files = files

    def get_file_content(self, repo: str, path: str) -> str:
        return self._files.get(path, "")


def test_fr8310_archive_bullet_is_already_covered():
    skill = (
        "# Harvest\n\n## Harvested lessons (intake)\n\n"
        "The bullet archive is lessons.md beside this file (FR #8310).\n"
    )
    archive = (
        "## Harvested lessons (intake)\n\n"
        "- MERGED MRB FINISH: opencode_typed_delivery must short-circuit on "
        "pr_state=MERGED (re-verify + DONE existing URL) and never emit FR "
        "commit/push/gh pr create steps (FR #8307 / #8286)\n"
    )
    filer = _Filer(
        {
            intake.SKILL_BOOK_PATHS["harvest"]: skill,
            intake.HARVEST_LESSONS_ARCHIVE: archive,
        }
    )
    covered = intake.harvest_book_text_for_dedupe(
        filer, "SimonBarnett/bobiverse", intake.SKILL_BOOK_PATHS["harvest"], skill
    )
    lesson = (
        "MERGED MRB FINISH: opencode_typed_delivery must short-circuit on "
        "pr_state=MERGED (re-verify + DONE existing URL) and never emit FR "
        "commit/push/gh pr create steps (FR #8307 / #8286)"
    )
    assert intake.lesson_sentence_already_in_book(covered, [lesson])
    assert intake.filter_new_lessons(covered, [lesson]) == []
    # New tip still appends only to SKILL.md, not the archive.
    new_md = intake.apply_lessons_to_skill_md(
        skill, ["brand new harvest tip about widgets"], covered_md=covered
    )
    assert "brand new harvest tip about widgets" in new_md
    assert "lessons.md" in new_md
