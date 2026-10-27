"""docs/mrb-5097 hostile pins for FR #5095 / PR #5097."""
from __future__ import annotations

from pathlib import Path

import shop_listen


def test_shop_listen_source_is_utf8_without_mojibake():
    root = Path(__file__).resolve().parents[2]
    raw = (root / "common" / "scripts" / "shop_listen.py").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\xc3\xa2\xe2\x82\xac" not in raw
    text = raw.decode("utf-8")
    assert "FR #5095" in text
    assert "never repo + id alone" in text or "never repo+id alone" in text


def test_format_shop_listen_info_notes_duplicate_done():
    line = shop_listen.format_shop_listen_info(
        {"verb": "DONE", "status": "duplicate", "task": "FIX", "repo": "o/r", "id": "#1"},
        nick="flamingo-1",
    )
    assert "duplicate-done-noop" in line
