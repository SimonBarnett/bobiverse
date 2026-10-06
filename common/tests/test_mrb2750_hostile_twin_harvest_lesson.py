"""MRB #2750 hostile: twin harvest-lesson playbook lives in job-mrb, not harvest."""
from __future__ import annotations

from pathlib import Path

HARVEST = (
    Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
)
JOB_MRB = (
    Path(__file__).resolve().parents[2]
    / "bob"
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


def test_mrb2750_job_mrb_has_harvest_lesson_twins_under_conflicting():
    text = _utf8_no_bom(JOB_MRB)
    assert "**Harvest-lesson twins:**" in text
    idx = text.index("**Harvest-lesson twins:**")
    window = text[idx : idx + 420]
    assert "FAIL-superseded" in window
    assert "bobiverse-bob-job-mrb" in window
    assert "2750" in window or "2741" in window or "2747" in window
    assert "misplaced raw duplicate" in window.lower() or "raw duplicate tip" in window


def test_mrb2750_job_mrb_harvest_lesson_step_4_twin_prs():
    text = _utf8_no_bom(JOB_MRB)
    assert "## Harvest-lesson intake PRs" in text or "Harvest-lesson intake PRs" in text
    assert "4. **Twin harvest-lesson PRs**" in text
    idx = text.index("4. **Twin harvest-lesson PRs**")
    window = text[idx : idx + 320]
    assert "FAIL-superseded" in window
    assert "merged first" in window.lower() or "citing the merged first" in window.lower()
    assert "2750" in window or "2741" in window or "2747" in window


def test_mrb2750_harvest_has_routing_tip_not_raw_twin_bullet():
    text = _utf8_no_bom(HARVEST)
    assert "## Harvested lessons (intake)" in text
    assert "bobiverse-bob-job-mrb" in text
    # Routing tip stays; raw Twin bullet must not reappear in harvest.
    assert "- Twin harvest-lesson PRs" not in text
    assert "**Harvest-lesson twins:**" not in text
    idx = text.index("- Harvest-lesson MRB playbooks")
    window = text[idx : idx + 420]
    assert "bobiverse-bob-job-mrb" in window
    assert "second copy" in window.lower() or "do not land a second copy" in window.lower()
