"""FR #6733: sid>0 without usable EnumWindows desktop must skip hidden-tray UI tests."""
from __future__ import annotations

from pathlib import Path

import pytest

import win_interactive_desktop as wid

ROOT = Path(__file__).resolve().parents[2]


def test_fr6733_skip_reason_names_issue_and_sessionname():
    reason = wid.HEADLESS_SID_SKIP_REASON
    assert "6733" in reason
    assert "SESSIONNAME" in reason or "EnumWindows" in reason or "desktop" in reason.lower()


def test_fr6733_skips_when_enum_probe_fails(monkeypatch):
    """Redqueen-class: sid>0, USERNAME set, SESSIONNAME empty, EnumWindows blind."""
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 2)
    monkeypatch.delenv("SESSIONNAME", raising=False)
    monkeypatch.setenv("USERNAME", "Administrator")
    monkeypatch.setattr(wid, "can_enum_visible_console_window", lambda **k: False)
    with pytest.raises(pytest.skip.Exception) as exc:
        wid.skip_unless_interactive_desktop()
    msg = str(exc.value)
    assert "6733" in msg
    assert "6729" not in msg


def test_fr6733_skips_when_open_input_desktop_fails(monkeypatch):
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 2)
    monkeypatch.setenv("SESSIONNAME", "Console")
    monkeypatch.setattr(wid, "open_input_desktop_ok", lambda: False)
    # can_enum_visible_console_window short-circuits on open_input_desktop_ok.
    with pytest.raises(pytest.skip.Exception) as exc:
        wid.skip_unless_interactive_desktop()
    assert "6733" in str(exc.value)


def test_fr6733_empty_sessionname_alone_does_not_skip_when_enum_ok(monkeypatch):
    """Interactive agent seats often omit SESSIONNAME while EnumWindows still works."""
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 1)
    monkeypatch.delenv("SESSIONNAME", raising=False)
    monkeypatch.setenv("USERNAME", "Administrator")
    monkeypatch.setattr(wid, "can_enum_visible_console_window", lambda **k: True)
    wid.skip_unless_interactive_desktop()


def test_fr6733_session0_still_uses_6729_reason(monkeypatch):
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 0)
    monkeypatch.delenv("SESSIONNAME", raising=False)
    with pytest.raises(pytest.skip.Exception) as exc:
        wid.skip_unless_interactive_desktop()
    assert "6729" in str(exc.value)


def test_fr6733_hidden_tray_doc_or_helper_cites_issue():
    text = (ROOT / "bob" / "tests" / "test_bob_worker_pack_020.py").read_text(encoding="utf-8")
    helper = (ROOT / "bob" / "tests" / "win_interactive_desktop.py").read_text(encoding="utf-8")
    assert "skip_unless_interactive_desktop" in text
    assert "6733" in text
    assert "6733" in helper
    assert "can_enum_visible_console_window" in helper
    assert "SESSIONNAME" in helper


def test_fr6733_live_probe_returns_bool_on_nt():
    if __import__("os").name != "nt":
        pytest.skip("windows")
    assert isinstance(wid.open_input_desktop_ok(), bool)
    assert isinstance(wid.can_enum_visible_console_window(timeout_s=1.5), bool)
