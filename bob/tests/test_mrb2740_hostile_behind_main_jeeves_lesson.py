"""MRB #2740 hostile: behind-main Jeeves status lesson folded into job-mrb (FR #2705)."""
from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)


def _utf8_no_bom(path: Path) -> str:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), path
    assert raw.endswith(b"\n"), path
    text = raw.decode("utf-8")
    for ln in text.splitlines():
        assert not ln.startswith("<<<<<<< "), path
        assert not ln.startswith("======= "), path
        assert not ln.startswith(">>>>>>> "), path
    return text


def test_mrb2740_lesson_on_behind_main_discipline_bullet():
    text = _utf8_no_bom(SKILL)
    assert "harvest #2740" in text
    assert "Behind-main + nits" in text
    # Contiguous: Jeeves status pins live on the behind-main bullet, not as a
    # fake 4th harvest-lesson review step.
    idx = text.index("harvest #2740")
    window = text[max(0, idx - 80) : idx + 350]
    assert "_process_started" in window
    assert "Build-Jeeves" in window or "Build-Jeeves.ps1" in window
    assert "VERSION" in window
    assert "docs/mrb" in window


def test_mrb2740_not_misplaced_under_harvest_lesson_review_steps():
    text = _utf8_no_bom(SKILL)
    start = text.index("## Harvest-lesson intake PRs (FR #2705)")
    end = text.index("## Skill / markdown diff hygiene")
    section = text[start:end]
    assert "Behind-main Jeeves status FRs:" not in section
    assert section.count("\n1. ") >= 1 and "Then merge" in section
