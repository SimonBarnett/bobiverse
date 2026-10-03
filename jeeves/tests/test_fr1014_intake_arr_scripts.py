"""MRB #1171 / FR #1014: Start-Jeeves + Assert-BobIntakeLocal contract locks."""
from __future__ import annotations

from pathlib import Path

JEEVES = Path(__file__).resolve().parents[1]
START = JEEVES / "scripts" / "Start-Jeeves.ps1"
ASSERT = JEEVES / "scripts" / "Assert-BobIntakeLocal.ps1"
EVIDENCE = JEEVES / "docs" / "fr-1014-intake-arr-restore.md"


def test_start_jeeves_waits_for_bobcallback_listen():
    text = START.read_text(encoding="utf-8")
    assert "Wait-BobCallbackListening" in text
    assert "7700" in text
    assert "BobCallback" in text
    assert "502.3" in text or "FR #1014" in text
    assert "Start-ScheduledTask" in text


def test_assert_intake_expects_http_202_local_and_public():
    text = ASSERT.read_text(encoding="utf-8")
    assert "127.0.0.1:7700" in text
    assert "irc.ntsa.uk" in text
    assert "/bob/v1/intake" in text
    assert "202" in text
    assert "SkipPublic" in text


def test_evidence_doc_covers_restore():
    text = EVIDENCE.read_text(encoding="utf-8")
    assert not EVIDENCE.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "502.3" in text
    assert "7700" in text
    assert "HTTP 202" in text
    assert "BobCallback" in text
