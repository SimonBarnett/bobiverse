"""FR #1601: inject_console submit gap + double Enter so Jeeves FROM lines auto-submit."""
from __future__ import annotations

import os

import bob_worker as bw


def test_submit_gap_default_is_0_20(monkeypatch):
    monkeypatch.delenv("BOB_WORKER_SUBMIT_GAP_S", raising=False)
    assert bw._submit_gap_s() == 0.20


def test_submit_gap_env_override_clamped(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_GAP_S", "0.01")
    assert bw._submit_gap_s() == 0.05
    monkeypatch.setenv("BOB_WORKER_SUBMIT_GAP_S", "9")
    assert bw._submit_gap_s() == 2.0
    monkeypatch.setenv("BOB_WORKER_SUBMIT_GAP_S", "0.35")
    assert bw._submit_gap_s() == 0.35


def test_submit_gap_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("BOB_WORKER_SUBMIT_GAP_S", "nope")
    assert bw._submit_gap_s() == 0.20


def test_inject_console_source_has_double_enter_and_no_006_default():
    src = (bw.__file__ and open(bw.__file__, encoding="utf-8").read()) or ""
    assert "def _submit_gap_s" in src
    assert "BOB_WORKER_SUBMIT_GAP_S" in src
    assert "enter2" in src
    assert "submit_gap_s: float = 0.06" not in src
    assert "default: float = 0.20" in src
    # FR #1601 comment trail
    assert "FR #1601" in src or "Too-short gaps (0.06s)" in src
