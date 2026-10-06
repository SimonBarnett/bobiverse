"""MRB #2749 hostile: harvest book routes harvest-lesson MRB playbooks to job-mrb."""
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


def test_mrb2749_harvest_routes_lesson_mrb_playbook_to_job_mrb():
    text = _utf8_no_bom(HARVEST)
    assert "## Harvested lessons (intake)" in text
    assert "bobiverse-bob-job-mrb" in text
    assert "2749" in text or "2740" in text
    assert "second copy" in text.lower() or "do not land a second copy" in text.lower()
    # Contiguous routing tip
    idx = text.index("bobiverse-bob-job-mrb")
    window = text[max(0, idx - 120) : idx + 220]
    assert "Harvest-lesson" in window or "harvest-lesson" in window.lower()
    assert "behind-main" in window.lower() or "1647" in window


def test_mrb2749_job_mrb_still_owns_behind_main_pins():
    text = _utf8_no_bom(JOB_MRB)
    assert "harvest #2740" in text
    assert "_process_started" in text
    assert "Behind-main + nits" in text


def test_mrb2749_harvest_keeps_sibling_lessons():
    text = _utf8_no_bom(HARVEST)
    assert "Clear-BobiverseJobWorktrees" in text
    assert "pr_exists" in text or "queue lock" in text
