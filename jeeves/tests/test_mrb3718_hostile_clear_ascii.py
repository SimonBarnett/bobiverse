"""docs/mrb-3718: hostile pin FR-3714 Clear.ps1 BOM-less ASCII (product #3718)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "common" / "scripts" / "Clear-BobiverseJobWorktrees.ps1"
PRODUCT_PIN = REPO / "jeeves" / "tests" / "test_fr3714_clear_bomless_ascii.py"


def test_mrb3718_clear_ps1_bomless_ascii_and_product_pin():
    raw = SCRIPT.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert all(ord(ch) <= 127 for ch in text), "Clear.ps1 must stay ASCII (FR #3714 / #3391)"
    assert "\u2014" not in text
    assert "skip this process ($PID) - Clear" in text
    pin = PRODUCT_PIN.read_text(encoding="utf-8")
    assert "test_fr3714_clear_job_worktrees_bomless_ascii" in pin
    assert "Clear-BobiverseJobWorktrees.ps1" in pin
