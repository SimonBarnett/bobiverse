"""FR #8759: bobiverse MSI lookup failure stays on /downloads with per-card errors.

Page-wide redirect to /downloads/error.html hid the Priority Agent card
(and any future static Plan card). Keep the grid; mark only failed
bobiverse product cards unavailable.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import REPO

DOWNLOADS = REPO / "jeeves" / "www" / "irc-ntsa" / "downloads"
INDEX = DOWNLOADS / "index.html"


def test_fr8759_index_has_no_page_wide_error_redirect():
    text = INDEX.read_text(encoding="utf-8")
    assert "window.location.href = '/downloads/error.html'" not in text
    assert "location.href='/downloads/error.html'" not in text.replace(" ", "")
    assert 'data-product="priority-agent"' in text
    assert 'src="/downloads/priority-agent.js"' in text


def test_fr8759_resolver_marks_failed_bobiverse_cards_in_place():
    text = INDEX.read_text(encoding="utf-8")
    assert "markCardUnavailable" in text or "Unavailable" in text
    # Fail path must touch bobiverse products only (bob/jeeves/airc), not navigate away.
    assert "api.github.com/repos/SimonBarnett/bobiverse/releases/latest" in text
    for product in ("bob", "jeeves", "airc"):
        assert f'data-product="{product}"' in text
    # Catch path must call the per-card helper (not redirect).
    assert ".catch(" in text
    assert "markCardUnavailable" in text


def test_fr8759_error_html_still_ships_for_direct_visits():
    err = DOWNLOADS / "error.html"
    assert err.is_file()
    t = err.read_text(encoding="utf-8")
    assert "Bob ear" in t
    assert 'data-product="priority-agent"' in t
