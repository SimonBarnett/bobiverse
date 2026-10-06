"""MRB #2842 hostile: FR #2811 MRB playbook in job-mrb; not harvest."""
from __future__ import annotations
from pathlib import Path

JOB_MRB = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = Path(__file__).resolve().parents[2] / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"
WORKER = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"

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

def test_mrb2842_fr2811_playbook_in_job_mrb_contiguous():
    text = _utf8_no_bom(JOB_MRB)
    assert "FR #2811 giveup/hold hostile MRB" in text
    idx = text.index("FR #2811 giveup/hold hostile MRB")
    window = text[max(0, idx - 40) : idx + 520]
    assert "hold_assigns_while" in window
    assert "held_until_turn_end" in window
    assert "post_bored" in window
    assert "2832" in window or "#2832" in window
    assert "docs/mrb" in window or "docs/mrb" in window.lower()
    section = text[text.index("## Harvest-lesson intake PRs"): text.index("## Skill / markdown diff hygiene")]
    assert "FR #2811 giveup/hold hostile MRB" in section
    assert "Wrong-book bob-worker" in section

def test_mrb2842_harvest_has_no_fr2811_hostile_mrb_copy():
    text = _utf8_no_bom(HARVEST)
    assert "Hostile MRB for FR #2811" not in text
    assert "hold_assigns_while" not in text
    assert "bobiverse-bob-job-mrb" in text

def test_mrb2842_worker_still_has_product_fr2811_pin():
    text = _utf8_no_bom(WORKER)
    assert "**FR #2811:** while the harvest hold" in text
