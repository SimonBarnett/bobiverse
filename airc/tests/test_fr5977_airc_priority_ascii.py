"""FR #5977: airc_priority.py stays ASCII (no U+2014) for fr5285 pin."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "scripts" / "airc_priority.py"


def test_fr5977_airc_priority_no_emdash_or_non_ascii():
    raw = WORKER.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8")
    assert "\u2014" not in text
    assert all(ord(ch) < 128 for ch in text)
    assert "_is_allowlist_absent_error" in text
