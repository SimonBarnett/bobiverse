"""FR #1472: Start-Jeeves user-context bobcallback fallback must prefer supervised wrapper."""
from __future__ import annotations

from pathlib import Path

START = Path(__file__).resolve().parents[1] / "scripts" / "Start-Jeeves.ps1"


def test_start_jeeves_prefers_supervised_for_user_context_fallback():
    text = START.read_text(encoding="utf-8-sig")
    assert "Start-BobCallbackSupervised.ps1" in text
    assert "FR #1472" in text or "FR #1455" in text
    # Both no-task and wedge fallbacks should launch via powershell supervised wrapper.
    assert text.count("Start-BobCallbackSupervised.ps1") >= 1
    assert "powershell.exe" in text


def test_start_jeeves_still_prefers_scheduled_task_first():
    text = START.read_text(encoding="utf-8-sig")
    i_task = text.find("Start-ScheduledTask -TaskName 'BobCallback'")
    i_sup = text.find("Start-BobCallbackSupervised.ps1")
    assert i_task > 0
    assert i_sup > i_task
