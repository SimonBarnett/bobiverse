"""Hostile MRB #5093: job-mrb skill must name jeeves/VISION.md (FR #5090)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"


def test_mrb5093_job_mrb_prefers_jeeves_vision():
    text = SKILL.read_text(encoding="utf-8")
    assert "jeeves/VISION.md" in text
    assert "FR #5090" in text
    # Contiguous product-vision window (bob / airc / jeeves).
    i = text.index("bob/VISION.md")
    window = text[i : i + 400]
    assert "airc/VISION.md" in window
    assert "jeeves/VISION.md" in window
