"""FR #7433: bob.ntsa.uk home links to https://plan.ntsa.uk (Plan skills)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / "jeeves" / "www" / "irc-ntsa" / "index.html"


def test_fr7433_home_has_plan_ntsa_uk_href():
    text = HOME.read_text(encoding="utf-8")
    assert "https://plan.ntsa.uk" in text
    assert 'href="https://plan.ntsa.uk"' in text or "href='https://plan.ntsa.uk'" in text
    # Short operator label near nav / Jeeves chrome.
    assert "Plan" in text
    low = text.lower()
    assert "plan skills" in low or "visionary" in low
    # Do not invent alternate hostnames.
    assert "plan.ntsa.com" not in low
    assert "skills-visionary.ntsa.uk" not in low
