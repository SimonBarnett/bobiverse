"""docs/mrb-5098: pin bobiverse-jeeves lesson — DONE match repo+id+task only."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"


def test_mrb5098_pins_done_match_repo_id_task_lesson():
    text = SKILL.read_text(encoding="utf-8-sig")
    assert "complete_job_by_ref" in text
    assert "repo+id+task" in text
    assert "never fall back to repo+id alone" in text
    assert "FR #4929 requeued MRB" in text
    # contiguous window
    i = text.find("complete_job_by_ref")
    assert i >= 0
    window = text[i : i + 220]
    assert "repo+id+task" in window
    assert "requeued MRB" in window