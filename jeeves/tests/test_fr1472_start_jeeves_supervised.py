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
    assert text.count("Start-BobCallbackUserContext -PythonExe") >= 2
    assert "powershell.exe" in text
    # Bare python Start-Process ($PythonExe) only inside the UserContext helper (last resort).
    i_fn = text.find("function Start-BobCallbackUserContext")
    i_bare = text.find("Start-Process -FilePath $PythonExe")
    assert i_fn > 0 and i_bare > i_fn
    assert text.count("Start-Process -FilePath $PythonExe") == 1
    assert "Start-BobCallbackSupervised.ps1 missing" in text
    # Call sites must not Start-Process bare $Python for bobcallback anymore.
    assert "Start-Process -FilePath $Python -ArgumentList $cbArgs" not in text


def test_start_jeeves_still_prefers_scheduled_task_first():
    text = START.read_text(encoding="utf-8-sig")
    i_task = text.find("Start-ScheduledTask -TaskName 'BobCallback'")
    # First *call* site (not the function definition).
    i_call = text.find("Start-BobCallbackUserContext -PythonExe")
    assert i_task > 0
    assert i_call > i_task
    assert "Prefer the durable scheduled task" in text
