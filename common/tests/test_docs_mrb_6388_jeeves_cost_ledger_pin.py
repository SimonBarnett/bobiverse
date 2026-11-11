"""docs/mrb-6388: jeeves-commands FR #6387 cost-ledger bullet is contiguous UTF-8."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docs_mrb_6388_jeeves_commands_cost_ledger_pin():
    raw = (ROOT / "jeeves" / "docs" / "jeeves-commands.md").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    # FR #6435 extended the heading to (FR #6387 / #6435); keep #6387 in the title
    # without requiring an immediate ')' after 6387 (that broke after #6435; FR #6611).
    assert "DONE cost ledger (FR #6387" in text
    assert "#6435" in text[text.index("DONE cost ledger") : text.index("DONE cost ledger") + 80]
    assert "`tokens_in=`" in text
    assert "`tokens_out=`" in text
    assert "`tokens_cached=`" in text
    assert "`job-cost-ledger.json`" in text
    assert "`job_costs.per_pr`" in text
    assert "	okens" not in text  # tab-mojibake of backtick+t
    needle = "`model=` / `tokens_in=` / `tokens_out=` / `tokens_cached=`"
    assert needle in text
    # Contiguous bullet still names per-job deltas / idempotent ledger key (FR #6435).
    window = text[text.index("DONE cost ledger") : text.index("DONE cost ledger") + 520]
    assert "per-job deltas" in window or "idempotently" in window
