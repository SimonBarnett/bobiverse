"""MRB #2560 hostile: harvest #1583 AppParameters log row must stay durable on main."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "common/docs/skill-harvest-log.md"


def test_mrb2560_harvest1583_section_is_contiguous():
    raw = LOG.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "<<<<<<" not in text and ">>>>>>" not in text
    idx = text.find("harvest #1583")
    assert idx >= 0, "main must keep durable harvest #1583 (FR #2559 / PR #2560)"
    window = text[max(0, idx - 200) : idx + 400]
    for needle in (
        "AppParameters",
        "airc-install.json",
        "ConsoleHome",
        "1552",
        "1570",
    ):
        assert needle in window, needle
    # Section heading must name the lesson (keeps keep-both races from dropping identity).
    assert "Airc MSI AppParameters identity preserve (harvest #1583)" in text


def test_mrb2560_harvest1583_not_only_alternate_1552():
    """Bare '1583' alone was too weak; require explicit harvest #1583 phrase."""
    text = LOG.read_text(encoding="utf-8")
    assert "harvest #1583" in text
    # Regression that failed on d7aeaa9 before PR #2560.
    assert text.count("harvest #1583") >= 1
