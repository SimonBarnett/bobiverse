"""MRB #2510 hostile: BOB_WORKER_INJECT_PASTE opt-out + skill hygiene (FR #2508)."""
from __future__ import annotations

from pathlib import Path

import bob_worker as bw
import pytest


def test_mrb2510_empty_env_defaults_paste_on(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "")
    assert bw._inject_prefer_paste() is True


def test_mrb2510_whitespace_zero_opts_out(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "  0  ")
    assert bw._inject_prefer_paste() is False


@pytest.mark.parametrize("val", ["yes", "true", "on", "2"])
def test_mrb2510_unknown_truthy_keeps_paste(monkeypatch, val):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", val)
    assert bw._inject_prefer_paste() is True


def test_mrb2510_opt_out_still_key_event_fallback(monkeypatch):
    if __import__("os").name != "nt":
        pytest.skip("windows")

    wrote = []
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "0")
    monkeypatch.setattr(bw, "_clipboard_get_unicode", lambda: "prior")
    monkeypatch.setattr(bw, "_clipboard_set_unicode", lambda t: (_ for _ in ()).throw(AssertionError("clipboard set")))
    monkeypatch.setattr(bw, "_clipboard_restore_unicode", lambda t: True)
    monkeypatch.setattr(bw, "_write_console_all", lambda *a, **k: wrote.append(a) or True)
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

    assert bw.inject_console(1, "FROM Jeeves hostile opt-out", submit_gap_s=0.05) is True
    # KEY_EVENT batch + two Enter chords (no Ctrl+V clipboard path)
    assert len(wrote) >= 3


def test_mrb2510_skill_documents_optout_no_c0():
    import re

    root = Path(__file__).resolve().parents[1]
    skill = root / ".grok" / "skills" / "bobiverse-bob-worker" / "SKILL.md"
    raw = skill.read_bytes()
    assert b"\x08" not in raw
    text = raw.decode("utf-8")
    assert "BOB_WORKER_INJECT_PASTE" in text
    assert "KEY_EVENT batch only" in text
    assert "bob-worker.exe" in text
    # Eaten leading letter must not remain on the inject-paste bullet
    # (bare name without the leading b; do not match inside bob-worker.exe)
    inject = [ln for ln in text.splitlines() if "Inject paste" in ln]
    assert inject, "inject paste bullet missing"
    assert "bob-worker.exe" in inject[0]
    assert re.search(r"(?<![A-Za-z])ob-worker\.exe", inject[0]) is None


def test_mrb2510_source_gate_prefer_paste_helper():
    src = Path(bw.__file__).read_text(encoding="utf-8")
    assert "def _inject_prefer_paste" in src
    assert 'raw not in ("0", "false", "no", "off")' in src
    assert "if _inject_prefer_paste():" in src
