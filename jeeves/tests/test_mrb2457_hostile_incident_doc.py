"""Hostile MRB #2457: incident note must stay docs-only and link heal playbooks."""
from __future__ import annotations

from repo_layout import ROOT

NOTE = ROOT / "jeeves" / "docs" / "empty-offer-incident-2026-10-05.md"
PLAYBOOK = ROOT / "jeeves" / "docs" / "empty-offer-playbook.md"
OPERATOR = ROOT / "jeeves" / "docs" / "empty-offer-operator.md"


def test_hostile_incident_links_heal_docs_and_has_no_bom():
    raw = NOTE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = NOTE.read_text(encoding="utf-8")
    assert "PR #2450" in text or "pull/2450" in text
    assert "#2446" in text
    assert "empty-offer-playbook.md" in text
    assert "empty-offer-operator.md" in text
    assert "win-mpre" in text  # mitigation seat named in timeline is OK as evidence
    # Must not embed install paths
    assert "C:\\ai\\jeeves" not in text
    assert "C:/ai/jeeves" not in text


def test_hostile_playbook_and_operator_exist():
    assert PLAYBOOK.is_file()
    assert OPERATOR.is_file()
    assert "empty-offer-incident-2026-10-05.md" in PLAYBOOK.read_text(encoding="utf-8")
