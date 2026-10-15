"""MRB #4326 hostile pin: FR #4317 HealEngine pre-start engine.alive leftovers."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
WATCH = ROOT / "bob" / "tray" / "tools" / "Watch-BobTray.ps1"


def test_mrb4326_is_stale_ignores_stamp_before_engine_start():
    t = CS.read_text(encoding="utf-8-sig")
    assert "FR #4317" in t
    i = t.find("public static bool IsStale")
    assert i > 0
    chunk = t[i : i + 1800]
    assert "engineStartedUtc" in chunk
    assert "m < engineStartedUtc" in chunk
    assert "return false" in chunk


def test_mrb4326_heal_logs_restart_storm():
    t = CS.read_text(encoding="utf-8-sig")
    i = t.find("void HealEngine()")
    chunk = t[i : i + 1800]
    assert "engine-restart-storm" in chunk


def test_mrb4326_watch_writes_engine_alive_before_queue():
    w = WATCH.read_text(encoding="utf-8")
    assert "FR #4317" in w
    i_tick = w.index("FR #4142: re-entrancy + per-tick timing")
    i_stamp = w.index("engine.alive", i_tick)
    i_q = w.index("Invoke-BobTrayStartWorkerQueue -Dir $script:startWorkerDir", i_tick)
    assert i_stamp < i_q
