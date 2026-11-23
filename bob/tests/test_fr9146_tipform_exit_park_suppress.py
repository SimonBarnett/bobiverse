"""FR #9146: TipForm Exit under #9011 park must not stop ircBob or 1440-suppress."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WATCH = ROOT / "tray" / "tools" / "Watch-BobTray.ps1"
LIFE = ROOT / "tray" / "tools" / "BobTrayLifecycle.ps1"
ENSURE = ROOT / "scripts" / "Ensure-BobTrayRunning.ps1"
START = ROOT / "scripts" / "Start-BobTray.ps1"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _exit_block() -> str:
    text = _txt(WATCH)
    start = text.find("function Invoke-BobTrayExit")
    end = text.find("function Get-BobTrayCursorHelpTooltip", start)
    assert start >= 0 and end > start
    return text[start:end]


def test_lifecycle_detects_park_markers():
    text = _txt(LIFE)
    assert "function Test-BobTrayExeParked" in text
    assert "bob-tray.exe.clickfix-park" in text
    assert "bob-tray.exe.clickfalse-park" in text
    assert "bob-tray.exe.clicktrue-park" in text


def test_park_exit_uses_short_suppress_and_park_via():
    block = _exit_block()
    assert "Test-BobTrayExeParked" in block
    assert "Exit-park" in block
    assert "TipForm-Exit-park" in block
    assert "TtlMinutes 5" in block or "TtlMinutes = 5" in block or "-TtlMinutes 5" in block
    assert "-StopService" not in block
    assert "Stop-BobTrayService" not in block


def test_non_park_exit_still_leaves_ircbob():
    block = _exit_block()
    assert "FR #9034" in block or "FR #9146" in block
    assert "left-running" in block or "left running" in block.lower()
    assert "Set-BobTrayWatchdogSuppress" in block


def test_ensure_heals_ircbob_even_when_suppress_active():
    text = _txt(ENSURE)
    assert "FR #9146" in text
    assert "ircbob-heal" in text
    # Heal must run before the suppress early-exit so ear recovers under TipForm-Exit.
    heal_at = text.find("ircbob-heal")
    skip_at = text.find("watchdog-skip-suppress")
    assert heal_at >= 0 and skip_at > heal_at


def test_start_bobtray_docs_exit_leaves_ear():
    text = _txt(START)
    assert "never stops ircBob" in text
    assert "#9146" in text
    # Legacy "Tray Exit stops ircBob" must be gone.
    assert "Tray Exit stops ircBob" not in text
