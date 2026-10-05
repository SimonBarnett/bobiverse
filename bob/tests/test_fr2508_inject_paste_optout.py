"""FR #2508: BOB_WORKER_INJECT_PASTE=0 skips clipboard paste inject."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import pytest


def test_fr2508_prefer_paste_default_on(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_INJECT_PASTE", raising=False)
    assert bw._inject_prefer_paste() is True
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    assert bw._inject_prefer_paste() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "FALSE", "No"])
def test_fr2508_prefer_paste_opt_out(monkeypatch, val):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", val)
    assert bw._inject_prefer_paste() is False


def test_fr2508_opt_out_skips_clipboard_set(monkeypatch):
    if __import__("os").name != "nt":
        pytest.skip("windows")

    sets = []
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "0")
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda: "prior")
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t: sets.append(t) or True)
    monkeypatch.setattr(bw, "_clipboard_restore_unicode", lambda t: True)
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

    assert bw.inject_console(1, "FROM Jeeves line for opt-out", submit_gap_s=0.05) is True
    assert sets == []


def test_fr2508_source_and_skill_document_env():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "BOB_WORKER_INJECT_PASTE" in src
    assert "FR #2508" in src
    skill = (
        Path(__file__).resolve().parents[1]
        / ".grok"
        / "skills"
        / "bobiverse-bob-worker"
        / "SKILL.md"
    )
    text = skill.read_text(encoding="utf-8")
    assert "BOB_WORKER_INJECT_PASTE" in text
