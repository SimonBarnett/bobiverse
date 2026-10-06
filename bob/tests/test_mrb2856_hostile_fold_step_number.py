"""MRB #2856 hostile: Fold Harvested-playbook step uniquely numbered 10."""
from __future__ import annotations
from pathlib import Path
import re

JOB_MRB = Path(__file__).resolve().parents[1] / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
HARVEST = Path(__file__).resolve().parents[2] / "common" / ".grok" / "skills" / "harvest" / "SKILL.md"

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

def test_mrb2856_fold_step_is_10_unique_in_intake_section():
    text = _utf8_no_bom(JOB_MRB)
    start = text.index("## Harvest-lesson intake PRs")
    end = text.index("## Skill / markdown diff hygiene")
    section = text[start:end]
    assert "Fold into existing Harvested playbook" in section
    assert "10. **Fold into existing Harvested playbook" in section
    assert "8. **Fold into existing Harvested playbook" not in section
    # Wrong-book remains step 8; FR #2811 remains step 9
    assert "8. **Wrong-book bob-worker product lesson" in section
    assert "9. **FR #2811 giveup/hold hostile MRB" in section
    nums = re.findall(r"(?m)^(\d+)\. \*\*Fold into existing Harvested playbook", section)
    assert nums == ["10"]

def test_mrb2856_harvest_has_no_fold_thin_meta_copy():
    text = _utf8_no_bom(HARVEST)
    assert "fold-thin-into-Harvested-playbook" not in text
