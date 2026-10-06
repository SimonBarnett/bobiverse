"""MRB #2735 hostile: harvest-lesson self-MRB lives under Self-MRB, not review steps."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
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


def test_mrb2735_self_mrb_section_names_harvest_lesson():
    text = _utf8_no_bom(JOB_MRB)
    assert "## Self-MRB" in text
    self_idx = text.index("## Self-MRB")
    harvest_idx = text.index("## Harvest-lesson intake PRs")
    section = text[self_idx:harvest_idx]
    assert "Harvest-lesson self-MRB" in section
    assert "Invoke-BobiverseHarvest" in section
    assert "NACK" in section and "GIVEUP" in section
    assert "2735" in section or "2732" in section
    assert "Confirm authorship" in section
    assert "harvest-lesson tip" in section or "lesson(<book>)" in section


def test_mrb2735_not_dangling_under_harvest_lesson_review_steps():
    text = _utf8_no_bom(JOB_MRB)
    # Review steps stay numbered 1-4; no orphan unnumbered self-MRB bullet between 3 and Twin.
    harvest = text[text.index("## Harvest-lesson intake PRs") : text.index("## Skill / markdown diff hygiene")]
    assert "4. **Twin harvest-lesson PRs**" in harvest
    assert "- A harvest-lesson PR opened from this seat's Invoke-BobiverseHarvest" not in harvest
