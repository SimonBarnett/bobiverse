"""FR #6546: bobiverse-airc SKILL matches FR #5190 (no default #bobiverse join)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

SKILL = ROOT / "airc" / ".grok" / "skills" / "bobiverse-airc" / "SKILL.md"


def test_fr6546_airc_skill_no_default_bobiverse_join():
    raw = SKILL.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "FR #5190" in text
    assert 'default `["#bobiverse"]`' not in text
    assert "also JOINs `#bobiverse`" not in text
    assert (
        "does not auto-join `#bobiverse`" in text
        or "must not auto-join `#bobiverse`" in text
    )
    # Opt-in presence still documented
    assert "presence_channels" in text
    assert "AIRC_PRESENCE_CHANNELS" in text
