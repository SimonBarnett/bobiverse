"""MRB #2749 hostile: harvest book routes harvest-lesson MRB playbooks to job-mrb."""
from __future__ import annotations

from pathlib import Path

HARVEST = (
    Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "SKILL.md"
)
LESSONS = (
    Path(__file__).resolve().parents[1] / ".grok" / "skills" / "harvest" / "lessons.md"
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
    archive = _utf8_no_bom(LESSONS)
    assert "## Harvested lessons (intake)" in text
    assert "lessons.md" in text
    assert "bobiverse-bob-job-mrb" in text
    # FR #8310: active placement rule lives in SKILL.md; archive keeps older tips.
    assert "2749" in archive or "2740" in archive
    assert "second copy" in text.lower() or "do not land a second copy" in text.lower()
    idx = text.index("Do not land a second copy of a harvest-lesson MRB playbook")
    window = text[idx : idx + 420]
    assert "bobiverse-bob-job-mrb" in window
    assert "behind-main" in archive.lower() or "1647" in archive
    assert "harvest" in window.lower()


def test_mrb2749_job_mrb_still_owns_behind_main_pins():
    text = _utf8_no_bom(JOB_MRB)
    assert "harvest #2740" in text
    assert "_process_started" in text
    assert "Behind-main + nits" in text


def test_mrb2749_harvest_keeps_sibling_lessons():
    archive = _utf8_no_bom(LESSONS)
    assert "Clear-BobiverseJobWorktrees" in archive
    assert "pr_exists" in archive or "queue lock" in archive
