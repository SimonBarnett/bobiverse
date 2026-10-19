"""docs/mrb-4838: pin stranded cross-job ACK -> GIVEUP (never invent DONE)."""
from __future__ import annotations

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-bob-worker"
    / "SKILL.md"
)


def test_mrb4838_stranded_ack_different_job_bullet_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    needle = "stranded ACK for a different job than this session completed"
    assert needle in text
    idx = text.index(needle)
    chunk = text[max(0, idx - 40) : idx + 200]
    assert "GIVEUP that ACK immediately" in chunk
    assert "never invent DONE" in chunk
    assert "FR work without a PR is not DONE" in chunk
    assert "\ufeff" not in text[:4]
