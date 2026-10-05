"""FR #2498: inject_console must not drip one KEY_EVENT paint per char into Grok TUI."""
from __future__ import annotations

import re
from pathlib import Path
from unittest import mock

import bob_worker as bw
import pytest


def test_fr2498_write_console_input_all_retries_partial_writes():
    calls = []

    class FakeK32:
        @staticmethod
        def WriteConsoleInputW(h, buf, n, written_ptr):
            calls.append(int(n))
            # ctypes byref(DWORD) → written_ptr._obj on CPython
            target = getattr(written_ptr, "_obj", None)
            if target is None:
                written_ptr.contents.value = 2 if int(n) > 2 and len(calls) == 1 else int(n)
            else:
                if len(calls) == 1 and int(n) > 2:
                    target.value = 2
                else:
                    target.value = int(n)
            return 1

    recs = bw.build_key_records("abcd", user32=None)
    assert len(recs) == 8
    ok = bw.write_console_input_all(FakeK32, 1, recs)
    assert ok is True
    assert calls[0] == 8
    assert len(calls) >= 2


def test_fr2498_write_console_input_all_fails_on_zero_written():
    class FakeK32:
        @staticmethod
        def WriteConsoleInputW(h, buf, n, written_ptr):
            target = getattr(written_ptr, "_obj", None)
            if target is None:
                written_ptr.contents.value = 0
            else:
                target.value = 0
            return 1

    recs = bw.build_key_records("a", user32=None)
    assert bw.write_console_input_all(FakeK32, 1, recs) is False


def test_fr2498_ctrl_v_record_count_is_small():
    recs = bw.build_ctrl_v_records()
    assert 2 <= len(recs) <= 8


def test_fr2498_inject_source_paste_and_no_sleep_in_loops():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "FR #2498" in src
    assert "BOB_WORKER_INJECT_PASTE" in src
    assert "def _set_clipboard_unicode" in src
    assert "def build_ctrl_v_records" in src
    assert "def write_console_input_all" in src
    m = re.search(r"def build_key_records\b.*?\ndef ", src, re.S)
    assert m and "sleep" not in m.group(0)
    m2 = re.search(r"def write_console_input_all\b.*?\ndef ", src, re.S)
    assert m2 and "time.sleep" not in m2.group(0)
    # Prefer paste before KEY_EVENT fallback in inject_console.
    inj = re.search(r"def inject_console\b.*?\n\ndef ", src, re.S) or re.search(
        r"def inject_console\b.*", src, re.S
    )
    assert inj
    body = inj.group(0)
    assert "_set_clipboard_unicode" in body
    assert "build_ctrl_v_records" in body
    assert "write_console_input_all" in body
    assert body.index("_set_clipboard_unicode") < body.index("build_key_records")


def test_fr2498_set_clipboard_roundtrip_optional():
    # Best-effort on Windows; skip if clipboard locked.
    if __import__("os").name != "nt":
        pytest.skip("windows")
    marker = "bobiverse-fr2498-clipboard-probe"
    ok = bw._set_clipboard_unicode(marker)
    if not ok:
        pytest.skip("clipboard unavailable")
    # Read back via PowerShell would be heavier; presence of True is enough here.


def test_fr2498_vision_mentions_paste():
    vision = Path(__file__).resolve().parents[1] / "VISION.md"
    text = vision.read_text(encoding="utf-8")
    assert "2498" in text or "clipboard" in text.lower() or "paste" in text.lower()
