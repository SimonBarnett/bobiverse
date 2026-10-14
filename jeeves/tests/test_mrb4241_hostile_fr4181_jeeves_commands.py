"""MRB #4241 hostile pins: FR #4181 out-of-fuel playbook in bobiverse-jeeves-commands.

Moved from harvest tip #4237 — durable home is jeeves-commands beside FR #2811.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "jeeves" / ".grok" / "skills" / "bobiverse-jeeves-commands" / "SKILL.md"


def test_jeeves_commands_fr4181_out_of_fuel_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    assert "FR #4181" in text
    assert "seat-out-of-fuel.json" in text
    assert "out-of-fuel" in text
    assert "giveup-offer" in text
    assert "fresh `!bored`" in text or "fresh !bored" in text
    assert "FR #2811" in text
    assert "do not park this under `harvest/SKILL.md`" in text
    assert "product PR #4190" in text or "PR #4190" in text
