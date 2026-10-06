"""MRB #2823 hostile: tip-current harvest-lesson fold lives in bobiverse-bob-job-mrb."""
from __future__ import annotations

from pathlib import Path

JOB_MRB = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)
HARVEST = (
    Path(__file__).resolve().parents[2]
    / "common"
    / ".grok"
    / "skills"
    / "harvest"
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


def test_mrb2823_tip_current_step_in_job_mrb_contiguous():
    text = _utf8_no_bom(JOB_MRB)
    assert "Tip current with main" in text
    idx = text.index("Tip current with main")
    window = text[max(0, idx - 40) : idx + 420]
    assert "path_fn" in window
    assert "events.jsonl" in window
    assert "docs/mrb" in window
    assert "UTF-8" in window or "no-BOM" in window or "no BOM" in window
    assert "2818" in window or "#2818" in window
    assert "2823" in window or "#2823" in window
    # Prior intake review steps stay in the same section (no orphan splice).
    section_start = text.index("## Harvest-lesson intake PRs")
    section_end = text.index("## Skill / markdown diff hygiene")
    section = text[section_start:section_end]
    assert "Tip current with main" in section
    assert "Twin harvest-lesson PRs" in section
    assert "CAST IRON already covers it" in section


def test_mrb2823_harvest_book_has_no_path_fn_tip_current_copy():
    text = _utf8_no_bom(HARVEST)
    assert "path_fn: tip current with main" not in text
    assert "Harvest-lesson MRB for bobiverse-bob-worker path_fn" not in text
