"""FR #6729: Session 0 / isolated SYSTEM suite cannot host clipboard or visible console UI."""
from __future__ import annotations

from pathlib import Path

import pytest

import win_interactive_desktop as wid

ROOT = Path(__file__).resolve().parents[2]


def test_fr6729_session_id_helper_returns_non_negative_int_on_nt():
    if __import__("os").name != "nt":
        pytest.skip("windows")
    sid = wid.current_windows_session_id()
    assert sid is not None
    assert isinstance(sid, int)
    assert sid >= 0


def test_fr6729_skip_unless_interactive_desktop_skips_session0(monkeypatch):
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 0)
    with pytest.raises(pytest.skip.Exception) as exc:
        wid.skip_unless_interactive_desktop()
    assert "6729" in str(exc.value)


def test_fr6729_skip_reason_names_session0_and_issue():
    reason = wid.SESSION0_SKIP_REASON
    assert "6729" in reason
    assert "Session 0" in reason
    assert "clipboard" in reason.lower() or "console" in reason.lower()


def test_fr6729_hidden_tray_calls_skip_helper():
    text = (ROOT / "bob" / "tests" / "test_bob_worker_pack_020.py").read_text(encoding="utf-8")
    assert "win_interactive_desktop" in text
    assert "skip_unless_interactive_desktop" in text
    assert "6729" in text


def test_fr6729_clipboard_inject_tests_force_paste_env():
    """start_agent(cursor|opencode) leaks BOB_WORKER_INJECT_PASTE=0 into later tests."""
    for name in (
        "test_fr2498_inject_batch_paste.py",
        "test_fr2504_clipboard_restore.py",
    ):
        text = (ROOT / "bob" / "tests" / name).read_text(encoding="utf-8")
        assert "6729" in text, name
        assert 'BOB_WORKER_INJECT_PASTE' in text, name
        assert 'setenv("BOB_WORKER_INJECT_PASTE", "1")' in text, name
