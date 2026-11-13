"""FR #6997: tray engine tick must not live-fetch Cursor / peer providers.

MarchHare 2.0.0: engine-stale at ~125s after start because Get-BobTrayHover called
Get-BobCursorAgentWeeklyRemaining (unbounded Get-CursorAgentUsage.py) on the
WinForms poll thread, so engine.alive stopped advancing past the 120s HealEngine
limit. Si rule: tray only reads what the bob service publishes.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

HOVER = ROOT / "third_party" / "bob-tray" / "src" / "Public" / "Get-BobTrayHover.ps1"
IRC = ROOT / "third_party" / "bob-tray" / "src" / "Private" / "Get-BobIrc.ps1"
WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr6997_cursor_fetch_default_is_cache_only():
    h = _txt(HOVER)
    fn = h[h.index("function Get-BobCursorAgentWeeklyRemaining") : h.index("function Resolve-BobCursorPython")]
    assert "AllowLiveFetch" in fn
    assert "if (-not $AllowLiveFetch)" in fn or "if(-not $AllowLiveFetch)" in fn.replace(" ", "")
    assert "WaitForExit" in fn
    assert "BOB_CURSOR_USAGE_FETCH_TIMEOUT_S" in fn
    # Live python path must be gated — default hover must not reach it.
    assert "Get-CursorAgentUsage.py" in fn or "Resolve-BobCursorUsageScript" in fn


def test_fr6997_hover_does_not_allow_live_cursor_fetch():
    h = _txt(HOVER)
    # The hover body must call the weekly helper without -AllowLiveFetch.
    i = h.index("function Get-BobTrayHover")
    body = h[i : i + 45000]
    assert "Get-BobCursorAgentWeeklyRemaining" in body
    assert "AllowLiveFetch" not in body.split("function Get-BobTrayHover", 1)[1][:45000] or (
        "-AllowLiveFetch" not in body
    )
    assert "-AllowLiveFetch" not in body[i : i + 45000]


def test_fr6997_hover_skips_peer_peek_when_digest_present():
    h = _txt(HOVER)
    i = h.index("function Get-BobTrayHover")
    body = h[i:]
    assert "digestPresent" in body
    assert "Skip UNC/DNS peer peeks" in body or "skip UNC/DNS peer peeks" in body.lower() or (
        "if ($digestPresent)" in body and "Read-BobPeerPeek" in body
    )
    # digest short-circuit appears before Read-BobPeerPeek in the empty-tile loop
    peek_i = body.index("Read-BobPeerPeek")
    assert "if ($digestPresent)" in body[:peek_i] or "digestPresent" in body[body.index("foreach ($mid in @($byMachine.Keys))") : peek_i]


def test_fr6997_write_bob_irc_status_no_live_cursor_fetch():
    t = _txt(IRC)
    fn = t[t.index("function Write-BobIrcStatus") : t.index("function Write-BobIrcStatus") + 8000]
    assert "Get-BobCursorAgentWeeklyRemaining" in fn
    assert "-AllowLiveFetch" not in fn
    assert "FR #6997" in fn or "6141" in fn


def test_fr6997_engine_alive_still_stamped_on_startworker_tick():
    w = _txt(WATCH)
    assert "engine.alive" in w
    assert "startWorkerTimer" in w or "startworker" in w.lower()
