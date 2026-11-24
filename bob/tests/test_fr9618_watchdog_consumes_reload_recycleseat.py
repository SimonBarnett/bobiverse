"""FR #9618: ThreadPool watchdog consumes tray-cmd reload and forces engine reload for pending recycleseat.

Redqueen ConPTY clear left req-*.json and tray-cmd reload unconsumed while engine_last_tick
froze: WinForms poll owns TakeReload, so a hung UI pump never reloads; recycleseat only runs
inside the PS engine tick. Watchdog (ThreadPool) must drain reload/wake and, when the engine
stamp is stale with pending recycleseat reqs, force ReloadEngine (bounded cooldown).
"""
from __future__ import annotations

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"
DOCS = ROOT / "bob" / "docs" / "bob-tray-dialogs.md"


def _cs() -> str:
    raw = CS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "BobTray.cs must stay UTF-8 without BOM"
    return raw.decode("utf-8")


def test_fr9618_watchdog_calls_consume_and_recycleseat_heal():
    t = _cs()
    assert "FR #9618" in t
    i = t.index("public void Watchdog()")
    j = t.index("void HealIrcBobIfIdle()", i)
    wd = t[i:j]
    assert "ConsumeHostReloadTriggers()" in wd
    assert "HealPendingRecycleSeatWhenEngineStale()" in wd
    assert "FR #9618" in wd


def test_fr9618_consume_host_reload_helper_takes_reload_and_wake():
    t = _cs()
    i = t.index("void ConsumeHostReloadTriggers()")
    chunk = t[i : i + 600]
    assert "TakeReload" in chunk
    assert "TakeWake" in chunk
    assert "engine.wake" in chunk
    assert "ReloadEngine()" in chunk
    # UI Reload path shares the helper
    i_reload = t.index("void Reload()")
    assert "ConsumeHostReloadTriggers()" in t[i_reload : i_reload + 500]


def test_fr9618_pending_recycleseat_forces_reload_when_engine_stale():
    t = _cs()
    assert "PendingRecycleSeatReqs" in t
    assert "lastRecycleForceReloadUtc" in t
    i_pend = t.index("bool PendingRecycleSeatReqs()")
    pend = t[i_pend : i_pend + 450]
    assert "recycleseat" in pend.lower()
    assert 'req-*.json' in pend
    i = t.index("void HealPendingRecycleSeatWhenEngineStale()")
    j = t.index("public void ReloadEngine()", i)
    heal = t[i:j]
    assert "PendingRecycleSeatReqs()" in heal
    assert "IsStale" in heal
    assert "ReloadEngine()" in heal
    assert "MaxAgeSeconds" in heal
    assert "fr9618-recycleseat-stale" in heal


def test_fr9618_docs_note_watchdog_reload():
    d = DOCS.read_text(encoding="utf-8")
    assert "9618" in d
    assert "recycleseat" in d.lower()
    assert "Watchdog" in d or "watchdog" in d.lower()
