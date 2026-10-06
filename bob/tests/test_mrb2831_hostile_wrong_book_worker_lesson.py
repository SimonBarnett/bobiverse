"""MRB #2831 hostile: wrong-book bob-worker FAIL-supersede rule in job-mrb."""
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


def test_mrb2831_wrong_book_worker_step_in_job_mrb_contiguous():
    text = _utf8_no_bom(JOB_MRB)
    assert "Wrong-book bob-worker product lesson" in text
    idx = text.index("Wrong-book bob-worker product lesson")
    window = text[max(0, idx - 40) : idx + 520]
    assert "2826" in window or "#2826" in window
    assert "2831" in window or "#2831" in window
    assert "FAIL-supersede" in window or "FAIL-supersede" in window.replace("\u2014", "-")
    assert "bobiverse-bob-worker" in window
    assert "harvest" in window.lower()
    assert "second copy" in window
    section_start = text.index("## Harvest-lesson intake PRs")
    section_end = text.index("## Skill / markdown diff hygiene")
    section = text[section_start:section_end]
    assert "Wrong-book bob-worker product lesson" in section
    assert "Nothing-queued" in section
    assert "Tip current with main" in section


def test_mrb2831_harvest_has_no_irc_classifier_fail_copy():
    text = _utf8_no_bom(HARVEST)
    assert "bob-worker IRC classifier" not in text
    assert "FAIL-supersede close the harvest PR unmerged" not in text
    assert "bobiverse-bob-job-mrb" in text
