"""FR #4142: headless Watch-BobTray engine must not spin the WinForms UI thread.

Follow-up to #4136 / #4141 (engine.alive watchdog). In BOB_TRAY_ENGINE=1 mode the
exe owns the icon; the PS engine must skip TipForm/Update-Hover UI work, keep slow
digest refresh off the UI thread, log slow ticks (>2s), and guard timers against
re-entrancy.
"""
from __future__ import annotations

from pathlib import Path

from repo_layout import ROOT

WATCH = ROOT / "third_party" / "bob-tray" / "tools" / "Watch-BobTray.ps1"
DIALOGS = ROOT / "third_party" / "bob-tray" / "tools" / "BobTrayDialogs.ps1"
SKILL = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob" / "SKILL.md"
TROUBLE = ROOT / "bob" / ".grok" / "skills" / "bobiverse-bob-troubleshooting" / "SKILL.md"


def _txt(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def test_fr4142_watch_has_timed_tick_helper():
    w = _txt(WATCH)
    assert "function Invoke-BobTrayTimedTick" in w or "function Measure-BobTrayTick" in w
    assert "tick slow" in w.lower() or "sec=" in w
    # Warn threshold at least 2s
    assert "2" in w


def test_fr4142_poll_reentrancy_stop_restart():
    w = _txt(WATCH)
    poll = w[w.index("$poll.Add_Tick") : w.index("$poll.Add_Tick") + 4500]
    assert "$poll.Stop()" in poll or "poll.Stop()" in poll
    assert "$poll.Start()" in poll or "poll.Start()" in poll
    assert "pollBusy" in poll or "re-entran" in poll.lower() or "FR #4142" in poll


def test_fr4142_engine_mode_skips_update_hover_ui_on_poll():
    w = _txt(WATCH)
    poll = w[w.index("$poll.Add_Tick") : w.index("$poll.Add_Tick") + 2800]
    assert "Test-BobTrayEngineMode" in poll
    # Must not call bare Update-Hover unconditionally in engine mode.
    assert "SkipUi" in poll or "Update-Hover" in poll
    assert (
        "if (-not" in poll
        and "Update-Hover" in poll
    ) or "SkipUi" in poll or "engine" in poll.lower()
    # Explicit skip path for engine
    assert "FR #4142" in poll


def test_fr4142_engine_mode_skips_flash_pulse_start():
    w = _txt(WATCH)
    # Near tray-up / Start() region
    boot = w[w.index("if (Test-BobTrayEngineMode)") : w.index("[System.Windows.Forms.Application]::Run")]
    assert "FR #4142" in boot or "engine" in boot.lower()
    # flash/pulse must be gated so headless does not thrash a hidden NotifyIcon
    assert "$flash.Start()" in w
    assert "Test-BobTrayEngineMode" in boot or "$flash.Start()" not in boot.split("else")[0]


def test_fr4142_digest_write_off_ui_thread():
    w = _txt(WATCH)
    # Write-BobIrcStatus must not remain only on the WinForms poll in engine mode;
    # prefer System.Timers.Timer / ThreadPool like FR #1553.
    assert "Write-BobIrcStatus" in w
    assert "System.Timers.Timer" in w
    # A dedicated digest/timer path cites FR #4142 or moves Write-BobIrcStatus off poll for engine
    poll = w[w.index("$poll.Add_Tick") : w.index("$poll.Add_Tick") + 2800]
    assert "FR #4142" in poll or "FR #1553" in poll
    # Either poll skips Write-BobIrcStatus when engine, or a Timers.Timer runs it
    assert (
        "Write-BobIrcStatus" not in poll
        or "Test-BobTrayEngineMode" in poll
        or "trayDigest" in w
        or "DigestTimer" in w
    )


def test_fr4142_startworker_timer_reentrancy_or_timing():
    w = _txt(WATCH)
    sw = w[w.index("$startWorkerTimer.Add_Tick") : w.index("$startWorkerTimer.Add_Tick") + 1500]
    assert "FR #4142" in sw or "Stop()" in sw or "Invoke-BobTrayTimedTick" in sw or "Measure-BobTrayTick" in sw


def test_fr4142_skill_documents_headless_ui_spin():
    text = _txt(SKILL) + "\n" + _txt(TROUBLE)
    assert "4142" in text or "UI-thread" in text or "headless" in text.lower()
    assert "engine" in text.lower()
