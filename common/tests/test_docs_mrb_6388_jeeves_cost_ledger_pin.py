"""docs/mrb-6388: jeeves-commands FR #6387 cost-ledger bullet is contiguous UTF-8."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docs_mrb_6388_jeeves_commands_cost_ledger_pin():
    text = (ROOT / "jeeves" / "docs" / "jeeves-commands.md").read_text(encoding="utf-8")
    assert "DONE cost ledger (FR #6387)" in text
    assert "`tokens_in=`" in text
    assert "`tokens_out=`" in text
    assert "`tokens_cached=`" in text
    assert "`job-cost-ledger.json`" in text
    assert "`job_costs.per_pr`" in text
    assert "	okens" not in text  # tab-mojibake of backtick+t
    needle = "`model=` / `tokens_in=` / `tokens_out=` / `tokens_cached=`"
    assert needle in text
