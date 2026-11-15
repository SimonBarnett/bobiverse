"""FR #7665: Stamp-PriorityAgentDownloads.ps1 must stay BOM-less ASCII."""
from __future__ import annotations

from pathlib import Path

STAMP = Path(__file__).resolve().parents[1] / "scripts" / "Stamp-PriorityAgentDownloads.ps1"


def test_fr7665_stamp_priority_agent_downloads_is_bomless_ascii():
    raw = STAMP.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "must stay BOM-less"
    assert all(b < 128 for b in raw), "must be pure ASCII (no em dash / smart punctuation)"
    text = raw.decode("ascii")
    assert "priority-agent - page" in text
    assert "\u2014" not in text
