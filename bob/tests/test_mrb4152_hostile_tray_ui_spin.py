"""Hostile pins for MRB #4152 / FR #4142 (headless engine skip TipForm UI spin)."""
from __future__ import annotations

from repo_layout import ROOT, resolve

WATCH = resolve("bob/tray/tools/Watch-BobTray.ps1")
SKILL = ROOT / "bob/.grok/skills/bobiverse-bob/SKILL.md"
TROUBLE = ROOT / "bob/.grok/skills/bobiverse-bob-troubleshooting/SKILL.md"


def _w() -> str:
    return WATCH.read_text(encoding="utf-8-sig")


def test_mrb4152_timed_tick_and_poll_reentrancy():
    w = _w()
    assert "function Invoke-BobTrayTimedTick" in w
    assert "tick slow" in w.lower()
    poll = w[w.index("$poll.Add_Tick") : w.index("$poll.Add_Tick") + 4500]
    assert "$poll.Stop()" in poll and "$poll.Start()" in poll
    assert "pollBusy" in poll
    assert "Update-Hover -SkipUi" in poll or "Update-Hover -SkipUi" in w
    assert "FR #4142" in poll


def test_mrb4152_engine_skips_flash_pulse_and_digest_on_timer():
    w = _w()
    assert "if (-not (Test-BobTrayEngineMode))" in w
    assert "$flash.Start()" in w and "$pulse.Start()" in w
    # flash/pulse Start must sit inside the engine-gated block region near Application.Run
    boot = w[w.index("# FR #4142: headless engine") : w.index("[System.Windows.Forms.Application]::Run")]
    assert "$flash.Start()" in boot
    assert "Test-BobTrayEngineMode" in boot
    assert "trayDigestTimer" in w
    assert "System.Timers.Timer" in w
    assert "SynchronizingObject = $null" in w or "SynchronizingObject=$null" in w


def test_mrb4152_skill_bullets():
    text = SKILL.read_text(encoding="utf-8") + "\n" + TROUBLE.read_text(encoding="utf-8")
    assert "FR #4142" in text or "#4142" in text
    assert "SkipUi" in text or "TipForm" in text or "UI-thread" in text or "headless" in text.lower()
    for p in (SKILL, TROUBLE):
        raw = p.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.endswith(b"\n")
