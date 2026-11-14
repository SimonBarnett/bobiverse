"""docs/mrb-7335: skill pins for FR #7334 no_eligible_reviewer idle-author recycle."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TROUBLE = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-troubleshooting" / "SKILL.md"
JEEVES = ROOT / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves" / "SKILL.md"


def test_docs_mrb_7335_troubleshooting_pins_fr7334():
    text = TROUBLE.read_text(encoding="utf-8")
    assert "FR #7334" in text
    assert "no_eligible_reviewer" in text
    assert "fewest" in text.lower() or "author_commit_counts" in text
    assert "recycleseat" in text


def test_docs_mrb_7335_jeeves_harvest_pins_fr7334():
    text = JEEVES.read_text(encoding="utf-8")
    assert "FR #7334" in text
    assert "maybe_recycle_stuck_no_eligible_reviewer" in text or "no_eligible_since" in text
