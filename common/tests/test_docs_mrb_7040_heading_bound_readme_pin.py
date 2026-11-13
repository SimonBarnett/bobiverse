"""docs/mrb-7040: hostile pin for fleet-ops heading-bound README ATX lesson."""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

SKILL = REPO / "common" / ".grok" / "skills" / "bobiverse-fleet-ops" / "SKILL.md"


def test_docs_mrb_7040_heading_bound_readme_atx_lesson_contiguous():
    text = SKILL.read_text(encoding="utf-8")
    needle = (
        "Heading-bound README pins must skip ATX detection inside fenced code; "
        "a # PowerShell comment is not a markdown heading."
    )
    assert needle in text
    i = text.index(needle)
    window = text[max(0, i - 40) : i + len(needle) + 40]
    assert "<<<<<<<" not in window and ">>>>>>>" not in window
