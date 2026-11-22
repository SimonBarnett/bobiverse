"""FR #8705 / BOB-56: bob.ntsa.uk docs for tray Agents/Workers menu tree."""
from __future__ import annotations

from repo_layout import ROOT

PAGE = ROOT / "jeeves" / "www" / "irc-ntsa" / "docs" / "tray" / "index.html"
HOME = ROOT / "jeeves" / "www" / "irc-ntsa" / "index.html"
EVIDENCE = ROOT / "bob" / "docs" / "bob-56-docs-tray-agents-workers-evidence.md"
MOCK = ROOT / "bob" / "docs" / "mocks" / "systray-agents-workers" / "home.html"


def test_evidence():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-56" in text
    assert "Agents" in text
    assert "Workers" in text


def test_tray_docs_match_menu_tree():
    page = PAGE.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    mock = MOCK.read_text(encoding="utf-8")
    # Top-level tree from BOB-06 / mock
    for label in ("Status", "Agents", "Workers", "Weights", "About", "Exit"):
        assert label in page, label
        assert label in mock, label
    # Agents children (not flat Plan sibling)
    for label in ("Plan", "Priority", "Jeeves"):
        assert label in page, label
    # Workers children
    for label in ("Grok", "Cursor", "Open Code"):
        assert label in page, label
    assert "docs/tray" in home or "docs/tray/index.html" in home
