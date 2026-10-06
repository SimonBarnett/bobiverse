"""MRB #2783 hostile: CAST IRON-covers-it FAIL-supersede tip lives in job-mrb."""
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


def test_mrb2783_job_mrb_has_cast_iron_covers_paragraph():
    text = _utf8_no_bom(JOB_MRB)
    assert "**CAST IRON already covers it" in text
    idx = text.index("**CAST IRON already covers it")
    window = text[idx : idx + 420]
    assert "FAIL-supersede" in window or "FAIL-superseded" in window
    assert "Harvested lessons" in window
    assert "2727" in window or "2732" in window or "2783" in window
    assert "Clear" in window or "removed=0" in window
    # Sits with Harvest-lesson twins under CONFLICTING
    twins = text.index("**Harvest-lesson twins:**")
    self_mrb = text.index("Self-MRB remains a separate hand-back")
    assert twins < idx < self_mrb


def test_mrb2783_harvest_lesson_intake_step_5():
    text = _utf8_no_bom(JOB_MRB)
    assert "5. **CAST IRON already covers it:**" in text
    idx = text.index("5. **CAST IRON already covers it:**")
    window = text[idx : idx + 280]
    assert "FAIL-supersede" in window
    assert "2783" in window or "2732" in window


def test_mrb2783_harvest_lacks_raw_cast_iron_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "- Harvest-lesson MRB: if the same skill book already has a CAST IRON" not in text
    assert "**CAST IRON already covers it" not in text
