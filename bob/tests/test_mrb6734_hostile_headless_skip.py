"""Hostile MRB #6734: can_enum must not spawn cmd when OpenInputDesktop fails."""
from __future__ import annotations

import pytest

import win_interactive_desktop as wid


def test_mrb6734_can_enum_does_not_popen_when_desktop_closed(monkeypatch):
    monkeypatch.setattr(wid, "open_input_desktop_ok", lambda: False)

    def boom(*_a, **_k):
        raise AssertionError("Popen must not run when OpenInputDesktop failed")

    monkeypatch.setattr(wid.subprocess, "Popen", boom)
    assert wid.can_enum_visible_console_window(timeout_s=0.5) is False


def test_mrb6734_sid_gt0_enum_ok_does_not_skip(monkeypatch):
    monkeypatch.setattr(wid, "current_windows_session_id", lambda: 2)
    monkeypatch.delenv("SESSIONNAME", raising=False)
    monkeypatch.setattr(wid, "can_enum_visible_console_window", lambda **k: True)
    wid.skip_unless_interactive_desktop()
