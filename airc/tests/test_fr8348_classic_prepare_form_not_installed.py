"""FR #8348: classic hosts see how to enable prepare-form when it is not installed."""
from __future__ import annotations

from pathlib import Path

import airc_priority as ap

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "airc" / "docs" / "airc-priority-client.md"


def test_fr8348_not_configured_stays_two_line_frame():
    blob = ap.format_priority_not_configured("aabb8348")
    lines = blob.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith(
        "err id=aabb8348 seq=1 code=not-configured reason=priority_not_installed"
    )
    assert lines[1] == "DONE id=aabb8348 exit=2"
    assert "PRIORITY prepare" not in lines[0]
    other = ap.format_priority_not_configured("aabb8348", reason="priority_allowlist_empty")
    assert len(other.splitlines()) == 2
    assert "DONE id=aabb8348 exit=2" in other


def test_fr8348_classic_doc_names_allowlist_credman_and_honesty_gate():
    text = DOC.read_text(encoding="utf-8")
    assert "### Classic self-hosted Test (FR #8348)" in text
    assert "priority-instances.example.json" in text
    assert "credentialTarget" in text
    assert "reason=priority_not_installed" in text
    assert "reason=session0_gui" in text
    assert "\neason=" not in text
    assert "session0_gui" in text
    assert "EXECPREPLOCK.UPD" in text
    assert "LASTPREPDATE" in text
