"""FR #3317: harvest-lesson short triage checklist in job-mrb."""
from __future__ import annotations
from pathlib import Path

JOB_MRB = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"

def test_fr3317_job_mrb_short_triage_contiguous():
    text = JOB_MRB.read_text(encoding="utf-8")
    section_start = text.index("## Harvest-lesson intake PRs")
    # FR #6662: section grew past a fixed 2200-char window (checklist now ~2132 in).
    # Bound to the next markdown H2 so the short-triage block stays contiguous.
    section_end = text.find("\n## ", section_start + 4)
    section = (
        text[section_start:section_end]
        if section_end > section_start
        else text[section_start : section_start + 12000]
    )
    assert "FR #3317" in section
    assert "Cost cap" in section
    assert "Short triage checklist (FR #3317)" in section
    idx = section.index("Short triage checklist (FR #3317)")
    window = section[idx : idx + 700]
    assert "Useful?" in window
    assert "Generalised?" in window
    assert "Non-duplicate?" in window
    assert "Vision / AGENTS fit?" in window
    assert "not-useful" in window
