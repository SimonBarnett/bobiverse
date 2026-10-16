"""Hostile pin: a harvest diary must not Closes an open product issue."""

from pathlib import Path


SKILL = (
    Path(__file__).resolve().parents[2]
    / "bob"
    / ".grok"
    / "skills"
    / "bobiverse-bob-job-mrb"
    / "SKILL.md"
)

NEEDLE = (
    "A harvest tip that only restates a product MRB and whose body Closes "
    "the product issue is FAIL-superseded. Do not merge it: that merge would "
    "close the product issue while the product tip is still open. The durable "
    "home is the product tip. Put Refs on the harvest tip, not Closes."
)


def test_harvest_tip_must_not_close_open_product_issue():
    text = SKILL.read_text(encoding="utf-8")
    assert not text.startswith("\ufeff")
    assert NEEDLE in text
    assert "\u2014" not in NEEDLE
