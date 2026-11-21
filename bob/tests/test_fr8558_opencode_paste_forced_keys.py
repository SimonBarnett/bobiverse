"""FR #8558: OpenCode ignores BOB_WORKER_INJECT_PASTE=1 (keys only).

Flamingo cli-failure on MRB #8554 showed stderr with a stray ``v`` and
``What would you like me to do?`` after PASTE=1 inject (#8560 ops note).
"""
from __future__ import annotations

import os

import bob_worker as bw


def test_fr8558_opencode_forces_keys_when_paste_1(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    logs: list[str] = []
    assert bw.apply_cursor_inject_keys_default("opencode", log=logs.append) is True
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"
    assert any("8558" in line or "8560" in line for line in logs)


def test_fr8558_opencode_already_zero_unchanged(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "0")
    assert bw.apply_cursor_inject_keys_default("opencode") is False
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "0"


def test_fr8558_cursor_explicit_paste_still_wins(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_INJECT_PASTE", "1")
    assert bw.apply_cursor_inject_keys_default("cursor") is False
    assert os.environ.get("BOB_WORKER_INJECT_PASTE") == "1"
