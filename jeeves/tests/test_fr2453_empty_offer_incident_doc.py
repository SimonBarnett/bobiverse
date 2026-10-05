"""FR #2453: dated empty-offer incident note links #2446 and PR #2450."""
from __future__ import annotations

from repo_layout import ROOT

NOTE = ROOT / "jeeves" / "docs" / "empty-offer-incident-2026-10-05.md"
PLAYBOOK = ROOT / "jeeves" / "docs" / "empty-offer-playbook.md"


def test_incident_note_exists_with_timeline_and_links():
    text = NOTE.read_text(encoding="utf-8")
    assert "2026-10-05" in text
    assert "nothing queued" in text.lower() or "nothing-queued" in text.lower() or "pins-only" in text.lower()
    assert "#2446" in text
    assert "#2450" in text or "pull/2450" in text
    assert "ce-priority" in text.lower() or "require_machine" in text
    assert "giveup" in text.lower() or "GIVEUP" in text
    assert "require_machine=ionos" not in NOTE.name  # path is docs-only


def test_playbook_links_incident_note():
    text = PLAYBOOK.read_text(encoding="utf-8")
    assert "empty-offer-incident-2026-10-05.md" in text
    assert "#2453" in text
