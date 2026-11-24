"""FR #9526: ReloadEngine clears HealEngine storm latch and sweeps orphan Watch-BobTray engines."""
from __future__ import annotations

from repo_layout import ROOT

CS = ROOT / "bob" / "tray" / "dialogs" / "BobTray.cs"


def test_fr9526_reload_engine_clears_storm_latch():
    raw = CS.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    t = raw.decode("utf-8")
    assert "FR #9526" in t
    i = t.index("public void ReloadEngine()")
    window = t[i : i + 2200]
    assert "engineStarts = 0" in window
    assert "engine.storm" in window
    assert "KillEngineTree" in window
    assert "StartEngine" in window
    assert "bob-tray-reload-fr9526" in window


def test_fr9526_kill_engine_tree_sweeps_orphans_and_stale_alive():
    t = CS.read_text(encoding="utf-8-sig")
    i = t.index("void KillEngineTree()")
    j = t.index("void ObserveWorkerSeats()")
    block = t[i:j]
    assert "KillOrphanTrayEngines" in block
    assert "EngineAliveStamp.FileName" in block
    k = t.index("void KillOrphanTrayEngines()")
    orphan = t[k:j]
    assert "Watch-BobTray" in orphan
    assert "taskkill" in orphan.lower() or "/PID" in orphan
