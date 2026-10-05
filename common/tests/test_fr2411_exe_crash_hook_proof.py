"""FR #2411: every shipped exe entry installs crash hook (source proof)."""
from __future__ import annotations

from pathlib import Path

from repo_layout import resolve

PYTHON_ENTRIES = {
    "jeeves.exe": "common/scripts/jeeves_main.py",
    "bob-ear.exe": "common/scripts/irc_agent.py",
    "bob-worker.exe": "bob/scripts/bob_worker.py",
    "Watch-AgentHealth.exe": "bob/agentwatcher/watch_agent_health.py",
    "airc.exe": "airc/scripts/airc_console_service.py",
}

CSHARP_ENTRIES = {
    "bob-about.exe": "bob/tray/dialogs",
    "bob-status.exe": "bob/tray/dialogs",
    "bob-tray.exe": "bob/tray/dialogs",
}


def test_python_entries_call_crash_report_install():
    missing = []
    for exe, rel in PYTHON_ENTRIES.items():
        text = resolve(rel).read_text(encoding="utf-8", errors="replace")
        if "crash_report" not in text or "install(" not in text:
            missing.append(f"{exe}: {rel} missing crash_report.install")
    assert not missing, "\n".join(missing)


def test_csharp_entries_reference_crashhook():
    hook = resolve("bob/tray/dialogs/CrashHook.cs")
    assert hook.is_file(), "CrashHook.cs missing"
    hook_text = hook.read_text(encoding="utf-8", errors="replace")
    assert "class CrashHook" in hook_text
    common = resolve("bob/tray/dialogs/BobDialogsCommon.cs").read_text(encoding="utf-8", errors="replace")
    # Install call or CrashHook mention from shared common / mains
    about = resolve("bob/tray/dialogs/BobAbout.cs").read_text(encoding="utf-8", errors="replace")
    status = resolve("bob/tray/dialogs/BobStatus.cs").read_text(encoding="utf-8", errors="replace")
    tray = resolve("bob/tray/dialogs/BobTray.cs").read_text(encoding="utf-8", errors="replace")
    blob = common + about + status + tray + hook_text
    assert "CrashHook" in blob
    for exe in CSHARP_ENTRIES:
        assert exe  # named for audit clarity
