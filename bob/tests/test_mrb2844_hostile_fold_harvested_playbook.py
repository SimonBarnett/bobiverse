"""MRB #2844 hostile: fold-into-Harvested-playbook lesson lives in bobiverse-bob-job-mrb."""
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


def test_mrb2844_fold_harvested_playbook_step_contiguous():
    text = _utf8_no_bom(JOB_MRB)
    assert "Fold into existing Harvested playbook" in text
    idx = text.index("Fold into existing Harvested playbook")
    window = text[max(0, idx - 40) : idx + 420]
    assert "bobiverse-jeeves-monitor" in window or "Harvested" in window
    assert "2803" in window or "Assign" in window
    assert "docs/mrb" in window
    assert "origin/main" in window or "behind" in window
    section_start = text.index("## Harvest-lesson intake PRs")
    section_end = text.index("## Skill / markdown diff hygiene")
    section = text[section_start:section_end]
    assert "Fold into existing Harvested playbook" in section
    assert "Tip current with main" in section


def test_mrb2844_harvest_book_has_no_monitor_fold_copy():
    text = _utf8_no_bom(HARVEST)
    assert "Harvest-lesson MRB for bobiverse-jeeves-monitor: fold thin" not in text
