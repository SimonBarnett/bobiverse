"""FR #8447: monitor skill must not tell bobiverse to pin via a title prefix."""

from pathlib import Path

SKILL = (
    Path(__file__).resolve().parents[1]
    / ".grok"
    / "skills"
    / "bobiverse-jeeves-monitor"
    / "SKILL.md"
)


def test_fr8447_bobiverse_pin_is_label_or_body_line():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4512" in text
    assert "needs-ionos:" in text
    assert "require_machine: ionos" in text
    assert "put the cue words in the **title** (or use `needs-ionos`)" not in text
