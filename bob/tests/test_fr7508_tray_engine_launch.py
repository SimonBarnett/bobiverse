"""FR #7508: bob-tray must spawn the engine, log failures, and never paint pre-start pools."""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"


def _cs() -> str:
    return CS.read_text(encoding="utf-8-sig")


def test_fr7508_start_engine_logs_attempt_and_failure():
    t = _cs()
    start = t[t.find("void StartEngine()") : t.find("void StartEngine()") + 2200]
    assert "engine-launch" in start
    assert "TrayLifecycle.Write" in start
    assert "catch" in start
    assert "engine-launch-fail" in start or "engine-launch-error" in start
    # must not silent-return on missing script without a log
    assert "engine-launch-miss" in start or "missing" in start.lower()


def test_fr7508_reload_ignores_pre_start_snapshot():
    t = _cs()
    reload = t[t.find("void Reload()") : t.find("void Reload()") + 1800]
    assert "engineStartedUtc" in reload
    assert "LastWriteTimeUtc" in reload
    assert "engine down" in t.lower() or "engine-down" in t.lower()


def test_fr7508_cold_start_grace_sixty_seconds():
    t = _cs()
    stamp = t[t.find("internal static class EngineAliveStamp") : t.find("internal static class EngineAliveStamp") + 2500]
    assert "ColdStartGraceSeconds" in stamp
    # FR #7564: grace is MaxAgeSeconds (120), not the old 60s window.
    assert "ColdStartGraceSeconds = MaxAgeSeconds" in stamp or "ColdStartGraceSeconds = 120" in stamp
    stale = stamp[stamp.find("IsStale") : stamp.find("IsStale") + 1200]
    # leftover pre-start stamp must become stale after grace (not return false forever)
    assert "ColdStartGraceSeconds" in stale or "ageSeconds >" in stale


def test_fr7508_heal_retries_when_engine_never_up():
    t = _cs()
    heal = t[t.find("void HealEngine()") : t.find("void HealEngine()") + 3500]
    assert "StartEngine()" in heal
    assert "engine-stale" in heal or "engine-launch" in t
