"""docs/mrb-6319: hostile pins for OpenCode reset docs (CodeRabbit amber on #6319)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBHOOKS = ROOT / "jeeves" / "docs" / "webhooks.md"


def test_docs_mrb6319_webhooks_pins_reset_rules():
    text = WEBHOOKS.read_text(encoding="utf-8")
    assert "reset unavailable" in text
    assert "past absolute" in text
    assert "deep-merging" in text
    assert "resetInSec" in text
    assert "go-zen" in text or "go zen" in text.lower()
    # Must not claim missing resetsAt alone always means unavailable when resetInSec exists.
    assert "even when" in text and "resetsAt` is absent" in text

def test_docs_mrb6319_webhooks_pins_resetinsec_wins_when_both_present():
    text = WEBHOOKS.read_text(encoding="utf-8")
    assert "resetInSec" in text and "resetsAt" in text
    assert "`resetInSec` wins" in text
    assert "_go_zen_meter_to_window" in text

