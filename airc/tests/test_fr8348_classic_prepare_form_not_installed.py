"""FR #8348: classic hosts see how to enable prepare-form when it is not installed."""
from __future__ import annotations

from pathlib import Path

import airc_priority as ap

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "airc" / "docs" / "airc-priority-client.md"


def test_fr8348_not_installed_names_classic_enable_step():
    blob = ap.format_priority_not_configured("aabb8348")
    assert "code=not-configured reason=priority_not_installed" in blob
    assert "priority-instances.example.json" in blob
    assert "credentialTarget" in blob
    assert "PRIORITY prepare-form" in blob
    assert "DONE id=aabb8348 exit=2" in blob
    other = ap.format_priority_not_configured("aabb8348", reason="priority_allowlist_empty")
    assert "priority-instances.example.json" not in other
    assert "DONE id=aabb8348 exit=2" in other


def test_fr8348_classic_doc_names_allowlist_credman_and_honesty_gate():
    text = DOC.read_text(encoding="utf-8")
    assert "### Classic self-hosted Test (FR #8348)" in text
    assert "priority-instances.example.json" in text
    assert "credentialTarget" in text
    assert "session0_gui" in text
    assert "EXECPREPLOCK.UPD" in text
    assert "LASTPREPDATE" in text
