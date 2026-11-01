"""FR #5799: skills document LEGION skipped profile=unchanged (FR #5782)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CMD = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-commands" / "SKILL.md"
TROUBLE = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc-troubleshooting" / "SKILL.md"


def test_fr5799_commands_document_skipped_profile():
    t = CMD.read_text(encoding="utf-8")
    assert not CMD.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "5782" in t
    assert "skipped" in t.lower()
    assert "unchanged" in t.lower()
    assert "profile_warn" in t


def test_fr5799_troubleshooting_documents_skipped_profile():
    t = TROUBLE.read_text(encoding="utf-8")
    assert not TROUBLE.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "5782" in t
    assert "skipped" in t.lower()
    assert "unchanged" in t.lower() or "profile_before" in t
