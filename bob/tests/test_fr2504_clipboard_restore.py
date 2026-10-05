"""FR #2504: inject paste must restore prior CF_UNICODETEXT clipboard after Ctrl+V."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import pytest


def test_fr2504_source_has_get_and_restore():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "FR #2504" in src
    assert "def _clipboard_get_unicode" in src
    assert "def _clipboard_restore_unicode" in src
    inj = src[src.index("def inject_console") :]
    assert "_clipboard_get_unicode" in inj
    assert "_clipboard_restore_unicode" in inj
    assert inj.index("_clipboard_set_unicode") < inj.index("_clipboard_restore_unicode")
    # Restore after submit gap so TUI can read clipboard for Ctrl+V.
    assert "clipboard_touched" in inj


def test_fr2504_inject_restores_prior_after_paste(monkeypatch):
    if __import__("os").name != "nt":
        pytest.skip("windows")

    prior = "operator-prior-clip"
    sets: list[str] = []
    restores: list[object] = []
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda: prior)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t: sets.append(t) or True)
    monkeypatch.setattr(
        bw, "_clipboard_restore_unicode", lambda t: restores.append(t) or True
    )
    monkeypatch.setattr(bw, "_write_console_all", lambda *a, **k: True)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)

    class _Fn:
        restype = None
        argtypes = None

        def __call__(self, *a, **k):
            return 99

    class FakeK32:
        CreateFileW = _Fn()
        CloseHandle = _Fn()
        WriteConsoleInputW = _Fn()

    class FakeU32:
        pass

    import ctypes

    def windll(name, use_last_error=True):
        return FakeK32() if "kernel32" in str(name).lower() else FakeU32()

    monkeypatch.setattr(ctypes, "WinDLL", windll)
    monkeypatch.setattr(bw.ctypes, "WinDLL", windll)

    ok = bw.inject_console(
        1, "FROM Jeeves #m n: MRB x#1 https://example", submit_gap_s=0.05
    )
    assert ok is True
    assert sets and "FROM Jeeves" in sets[0]
    assert restores == [prior]


def test_fr2504_inject_restores_none_when_prior_empty(monkeypatch):
    if __import__("os").name != "nt":
        pytest.skip("windows")

    restores: list[object] = []
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda: None)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t: True)
    monkeypatch.setattr(
        bw, "_clipboard_restore_unicode", lambda t: restores.append(t) or True
    )
    monkeypatch.setattr(bw, "_write_console_all", lambda *a, **k: True)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)

    class _Fn:
        restype = None
        argtypes = None

        def __call__(self, *a, **k):
            return 99

    class FakeK32:
        CreateFileW = _Fn()
        CloseHandle = _Fn()
        WriteConsoleInputW = _Fn()

    class FakeU32:
        pass

    import ctypes

    def windll(name, use_last_error=True):
        return FakeK32() if "kernel32" in str(name).lower() else FakeU32()

    monkeypatch.setattr(ctypes, "WinDLL", windll)
    monkeypatch.setattr(bw.ctypes, "WinDLL", windll)

    assert bw.inject_console(1, "hello world line", submit_gap_s=0.05) is True
    assert restores == [None]


def test_fr2504_restore_helper_delegates_to_set(monkeypatch):
    seen = []
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t: seen.append(t) or True)
    assert bw._clipboard_restore_unicode("abc") is True
    assert seen == ["abc"]
