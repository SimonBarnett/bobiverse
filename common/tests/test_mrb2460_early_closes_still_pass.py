"""MRB #2460: a harvest tip that already closed the issue does not block product PASS."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = (
    ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-job-mrb" / "SKILL.md"
)
NEEDLE = (
    "When a harvest tip already closed the product issue, still PASS and "
    "merge the product tip. Note the early close as ACCEPTABLE. Reuse the "
    "docs/mrb hostile pin."
)


def test_mrb2460_early_closes_still_pass():
    skill = SKILL.read_text(encoding="utf-8")
    start = skill.find("## Harvested MRB discipline")
    end = skill.find("## Harvest digest", start)
    assert start >= 0 and end > start
    window = skill[start:end]
    assert NEEDLE in window
