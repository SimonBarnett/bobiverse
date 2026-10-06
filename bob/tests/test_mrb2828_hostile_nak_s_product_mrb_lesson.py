"""MRB #2828 hostile: nothing-queued nak_s playbook lives in bobiverse-bob-job-mrb."""
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
WORKER = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
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


def test_mrb2828_nak_s_product_mrb_step_in_job_mrb_contiguous():
    text = _utf8_no_bom(JOB_MRB)
    assert "Nothing-queued" in text
    assert "nak_s" in text
    idx = text.index("Nothing-queued `nak_s` product MRB")
    window = text[max(0, idx - 40) : idx + 520]
    assert "2825" in window or "#2825" in window
    assert "2828" in window or "#2828" in window
    assert "2806" in window or "#2806" in window
    assert "docs/mrb" in window or "docs/mrb-N" in window
    assert "nak-beats-repeat_s" in window
    assert "ACCEPTABLE drift" in window
    assert "repeat_s" in window
    assert "harvest" in window.lower()
    # Same Harvest-lesson intake section as tip-current step
    section_start = text.index("## Harvest-lesson intake PRs")
    section_end = text.index("## Skill / markdown diff hygiene")
    section = text[section_start:section_end]
    assert "Nothing-queued `nak_s` product MRB" in section
    assert "Tip current with main" in section


def test_mrb2828_harvest_has_no_nak_s_playbook_copy():
    text = _utf8_no_bom(HARVEST)
    assert "Hostile MRB for nothing-queued nak_s" not in text
    assert "nak-beats-repeat_s pin" not in text
    # Ownership pointer remains
    assert "bobiverse-bob-job-mrb" in text


def test_mrb2828_worker_still_has_fr2806_product_pin():
    text = _utf8_no_bom(WORKER)
    assert "FR #2806" in text
    idx = text.index("FR #2806")
    # FR #2806 sits late in the !bored paragraph; look back for nak_s / reason=nak.
    window = text[max(0, idx - 220) : idx + 180]
    assert "nak_s" in window or "reason=nak" in window
    assert "repeat_s" in window
