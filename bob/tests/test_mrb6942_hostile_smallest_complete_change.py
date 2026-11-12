"""MRB #6942 hostile pins for FR #6940 smallest-complete-change skill."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "common" / ".grok" / "skills" / "smallest-complete-change" / "SKILL.md"
JOB_BOOKS = [
    REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-fr" / "SKILL.md",
    REPO / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md",
    REPO / "common" / ".grok" / "skills" / "harvest" / "SKILL.md",
]


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        return text.split("---", 2)[1]
    return text[:500]


def test_mrb6942_skill_empty_depends_and_credits():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    fm = _frontmatter(SKILL)
    assert "name: smallest-complete-change" in fm
    assert "depends_on: []" in fm
    assert "Dietrich Gebert" in text
    assert "MIT" in text
    assert "does not change ACK/DONE" in text or "does not replace" in text.lower()


def test_mrb6942_job_books_do_not_hard_depend():
    for book in JOB_BOOKS:
        assert book.is_file(), book
        head = _frontmatter(book)
        assert "smallest-complete-change" not in head, book.name
