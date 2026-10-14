"""MRB #4190 docs pin: jeeves-commands documents FR #4181 out-of-fuel skip."""
from __future__ import annotations

from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs" / "jeeves-commands.md"


def test_jeeves_commands_documents_out_of_fuel_giveup_offer_skip():
    text = DOCS.read_text(encoding="utf-8")
    assert "GIVEUP `out-of-fuel` (FR #4181)" in text
    assert "giveup-offer skipped" in text
    assert "seat-out-of-fuel.json" in text
    assert "clears the mark" in text or "clear" in text.lower()
