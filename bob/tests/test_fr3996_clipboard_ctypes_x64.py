"""FR #3996: x64-safe clipboard ctypes + batched KEY_EVENT fallback (no drip)."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import bob_worker as bw
import pytest

SRC = Path(__file__).resolve().parents[1] / "scripts" / "bob_worker.py"

ASSIGN = (
    "FROM Jeeves #win-mpre8vi4u6u win-mpre8vi4u6u-15220: "
    "MRB SimonBarnett/bobiverse#3996 https://github.com/SimonBarnett/bobiverse/pull/3996"
)


class _Fn:
    restype = None
    argtypes = None

    def __call__(self, *a, **k):
        return 99


def _fake_k32():
    class FakeK32:
        CreateFileW = _Fn()
        CloseHandle = _Fn()
        WriteConsoleInputW = _Fn()

    return FakeK32()


def test_fr3996_source_gates_ctypes_and_fallback():
    src = SRC.read_text(encoding="utf-8")
    assert "FR #3996" in src
    assert "_configure_clipboard_winapi" in src
    assert "GlobalAlloc.restype" in src
    assert "SetClipboardData.restype" in src
    assert "clipboard_fallback" in src
    assert "step=" in src
    # Must not hard-fail long paste-preferred lines without a batch KEY fallback.
    assert "reason=clipboard_fallback" in src


def test_fr3996_configure_sets_hglobal_prototypes():
    if os.name != "nt":
        pytest.skip("windows")
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    u32 = ctypes.WinDLL("user32", use_last_error=True)
    bw._configure_clipboard_winapi(k32, u32)
    assert k32.GlobalAlloc.restype is ctypes.c_void_p
    assert k32.GlobalLock.restype is ctypes.c_void_p
    assert u32.SetClipboardData.restype is ctypes.c_void_p
    assert u32.GetClipboardData.restype is ctypes.c_void_p
    assert list(k32.GlobalAlloc.argtypes)[0] is ctypes.c_uint
    assert list(k32.GlobalAlloc.argtypes)[1] is ctypes.c_size_t


def test_fr3996_clipboard_set_unicode_roundtrip_real():
    """Acceptance: real _clipboard_set_unicode on Windows x64 (not a mock)."""
    if os.name != "nt":
        pytest.skip("windows")
    marker = "bobiverse-fr3996-clipboard-" + os.urandom(4).hex()
    prior = bw._clipboard_get_unicode(log=None)
    try:
        assert bw._clipboard_set_unicode(marker, log=None) is True
        got = bw._clipboard_get_unicode(log=None)
        assert got == marker, (got, marker)
    finally:
        # best-effort restore
        try:
            bw._clipboard_restore_unicode(prior, log=None)
        except Exception:
            pass


def test_fr3996_clipboard_fail_uses_batched_keys_not_hard_fail(monkeypatch):
    """On clipboard set fail, one batched KEY_EVENT write — never path=fail for long assign."""
    if os.name != "nt":
        pytest.skip("windows")

    logs: list[str] = []
    key_calls = []

    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda log=None: None)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda text, log=None: False)
    monkeypatch.setattr(
        bw,
        "build_key_records",
        lambda text, user32=None: key_calls.append(text) or bw.build_enter_records(),
    )
    monkeypatch.setattr(bw, "_write_console_all", lambda *a, **k: True)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        bw.ctypes,
        "WinDLL",
        lambda name, use_last_error=True: _fake_k32() if "kernel32" in name.lower() else SimpleNamespace(),
    )

    assert bw.inject_console(0, ASSIGN, log=logs.append) is True
    assert key_calls == [ASSIGN]
    assert any("path=keys" in m and "clipboard_fallback" in m for m in logs), logs
    assert not any("path=fail" in m and "no KEY_EVENT drip" in m for m in logs), logs
