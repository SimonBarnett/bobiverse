"""docs/mrb-5138: empty-offer-operator prefers !cleargiveup (FR #5135)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "jeeves" / "docs" / "empty-offer-operator.md"


def test_empty_offer_operator_prefers_cleargiveup():
    text = DOC.read_text(encoding="utf-8")
    assert "!cleargiveup owner/repo#N" in text
    assert "Preferred (FR #5135)" in text
    assert "ledger_clear_giveup" in text  # fallback retained


def test_jeeves_commands_cleargiveup_not_marked_unimplemented():
    cmd = ROOT / "jeeves" / "docs" / "jeeves-commands.md"
    text = cmd.read_text(encoding="utf-8")
    assert "!cleargiveup" in text
    assert "(not implemented)" not in text
    assert "Preferred (FR #5135)" in text or "FR #5135" in text
