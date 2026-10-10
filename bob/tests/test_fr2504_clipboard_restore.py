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
    # MRB #2506: docstring must stay "Paste text" (no tab / mangled `text`).
    assert '"""Paste text into THIS process' in inj
    assert "Paste \text" not in inj.replace("Paste text", "")
    assert "\ttext" not in inj.split('"""', 2)[1]




def test_fr2504_inject_restores_prior_after_paste(monkeypatch):
    if __import__("os").name != "nt":
        pytest.skip("windows")

    prior = "operator-prior-clip"
    sets: list[str] = []
    restores: list[object] = []
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda log=None: prior)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t, log=None: sets.append(t) or True)
    monkeypatch.setattr(
        bw, "_clipboard_restore_unicode", lambda t, log=None: restores.append(t) or True
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
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda log=None: None)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t, log=None: True)
    monkeypatch.setattr(
        bw, "_clipboard_restore_unicode", lambda t, log=None: restores.append(t) or True
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
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t, log=None: seen.append(t) or True)
    assert bw._clipboard_restore_unicode("abc") is True
    assert seen == ["abc"]


def _fake_win_dlls(monkeypatch):
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


def test_mrb2506_restore_after_gap_before_enter(monkeypatch):
    """Hostile: restore runs after submit-gap sleep and before first Enter write."""
    if __import__("os").name != "nt":
        pytest.skip("windows")

    prior = "prior-clip-mrb"
    events: list[str] = []

    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda log=None: prior)
    monkeypatch.setattr(
        bw, "_clipboard_set_unicode", lambda t, log=None: events.append(f"set:{t[:12]}") or True
    )
    monkeypatch.setattr(
        bw,
        "_clipboard_restore_unicode",
        lambda t, log=None: events.append(f"restore:{t}") or True,
    )

    def write_all(_k32, _h, recs, _wt):
        # Enter records are short; Ctrl+V / key batches are longer.
        n = len(recs) if hasattr(recs, "__len__") else 0
        events.append(f"write:{n}")
        return True

    monkeypatch.setattr(bw, "_write_console_all", write_all)
    monkeypatch.setattr(
        bw.time, "sleep", lambda s: events.append(f"sleep:{s}") or None
    )
    _fake_win_dlls(monkeypatch)

    assert bw.inject_console(1, "FROM line for order check", submit_gap_s=0.05) is True
    assert events[0].startswith("set:")
    assert "sleep:0.05" in events
    ri = events.index(f"restore:{prior}")
    si = events.index("sleep:0.05")
    assert si < ri, events
    # At least one Enter write after restore.
    assert any(e.startswith("write:") for e in events[ri + 1 :]), events


def test_mrb2506_finally_restores_on_early_key_fail(monkeypatch):
    """Hostile: if KEY_EVENT fallback write fails after clipboard set, finally restores."""
    if __import__("os").name != "nt":
        pytest.skip("windows")

    prior = "early-fail-prior"
    restores: list[object] = []
    calls = {"n": 0}

    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda log=None: prior)
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t, log=None: True)
    monkeypatch.setattr(
        bw, "_clipboard_restore_unicode", lambda t, log=None: restores.append(t) or True
    )

    def write_all(_k32, _h, recs, _wt):
        calls["n"] += 1
        # First write is Ctrl+V chord -> fail so KEY_EVENT path runs; second fails hard.
        return False

    monkeypatch.setattr(bw, "_write_console_all", write_all)
    monkeypatch.setattr(bw.time, "sleep", lambda s: None)
    _fake_win_dlls(monkeypatch)

    assert bw.inject_console(1, "will fail key path", submit_gap_s=0.05) is False
    assert restores == [prior]
