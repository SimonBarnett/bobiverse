"""FR #6810: vision-cli-token-compare allows Cursor live chat-dir read (post #6782)."""
from __future__ import annotations

from pathlib import Path

VISION = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "vision-cli-token-compare-2026-11-12.md"
)


def test_fr6810_vision_no_bom():
    raw = VISION.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")


def test_fr6810_vision_allows_cursor_live_chat_dir_read():
    text = VISION.read_text(encoding="utf-8")
    # Old inventory forbade a live reader; that contradicts landed FR #6782 / S2.
    assert "No live store reader" not in text
    assert "Cursor stamps only `BOB_CURSOR_USAGE_PATH` or `run/cursor-usage.json`" not in text
    # Positive: fixture path kept; live bound seat chat-dir when non-zero; no dashboard.
    assert "BOB_CURSOR_USAGE_PATH" in text or "run/cursor-usage.json" in text
    assert "chat" in text.lower() and (
        "live" in text.lower() or "bound" in text.lower()
    )
    assert "dashboard" in text.lower()
    # S2 success row already matches FR-002.
    assert "#6782" in text or "FR-002" in text or "S2" in text
