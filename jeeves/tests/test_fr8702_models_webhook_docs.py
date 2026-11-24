"""FR #8702 / BOB-05: bob.ntsa.uk docs page for GET /bob/v1/models."""
from __future__ import annotations

from repo_layout import ROOT

INDEX = ROOT / "jeeves" / "www" / "irc-ntsa" / "docs" / "webhooks" / "index.html"
PAGE = ROOT / "jeeves" / "www" / "irc-ntsa" / "docs" / "webhooks" / "models.html"
EVIDENCE = ROOT / "bob" / "docs" / "bob-05-models-webhook-docs-evidence.md"


def test_evidence():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert "BOB-05" in text
    assert "/bob/v1/models" in text


def test_models_page_and_index_link():
    page = PAGE.read_text(encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    assert "/bob/v1/models" in page
    assert "models.html" in index
    assert "/bob/v1/models" in index
    assert "GET" in page