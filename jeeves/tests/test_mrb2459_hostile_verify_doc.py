"""Hostile MRB #2459: verify snapshot stays docs-only and links heal/incident notes."""
from __future__ import annotations

from repo_layout import ROOT

DOC = ROOT / "jeeves" / "docs" / "empty-offer-verify-2454.md"
PLAY = ROOT / "jeeves" / "docs" / "empty-offer-playbook.md"


def test_hostile_verify_doc_links_and_no_install_paths():
    raw = DOC.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = DOC.read_text(encoding="utf-8")
    assert "FR #2454" in text
    assert "#2450" in text or "PR #2450" in text
    assert "empty-offer-playbook.md" in text
    assert "empty-offer-incident-2026-10-05.md" in text
    assert "empty-offer-operator.md" in text
    assert "Postscript" in text
    assert "C:\\ai\\jeeves" not in text
    assert "Invoke-RestMethod" in text


def test_hostile_playbook_lists_verify_and_incident():
    text = PLAY.read_text(encoding="utf-8")
    assert "empty-offer-verify-2454" in text
    assert "empty-offer-incident-2026-10-05" in text
