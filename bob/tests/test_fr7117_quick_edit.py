"""FR #7117: seat consoles must disable QuickEdit (no Enter-to-unfreeze)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw


def test_fr7117_ensure_console_clears_quick_edit():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "disable_console_quick_edit" in src
    assert "ENABLE_QUICK_EDIT_MODE" in src
    i = src.find("def ensure_console")
    body = src[i : src.find("\ndef ", i + 1)]
    assert "disable_console_quick_edit" in body


def test_fr7117_quick_edit_bit_is_0x40():
    assert bw.ENABLE_QUICK_EDIT_MODE == 0x40
    assert bw.ENABLE_EXTENDED_FLAGS == 0x80
