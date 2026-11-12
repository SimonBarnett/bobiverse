"""Detect a Windows interactive desktop vs Session 0 (isolated SYSTEM / service).

FR #6729: flamingo !build runs pytest as ircBob (LocalSystem, Session 0).
That window station has no visible ConsoleWindowClass and no usable user
clipboard. Tests that EnumWindows a visible console, or that exercise the
real OpenClipboard / CONIN$ path, must skip with a durable reason instead of
failing the release suite.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

SESSION0_SKIP_REASON = (
    "FR #6729: Session 0 (non-interactive / isolated SYSTEM suite) cannot host "
    "clipboard or visible console UI"
)


def current_windows_session_id() -> int | None:
    """Return this process's Terminal Services session id, or None if unknown."""
    if os.name != "nt":
        return None
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.ProcessIdToSessionId.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        k32.ProcessIdToSessionId.restype = wintypes.BOOL
        sid = wintypes.DWORD()
        if not k32.ProcessIdToSessionId(os.getpid(), ctypes.byref(sid)):
            return None
        return int(sid.value)
    except Exception:
        return None


def skip_unless_interactive_desktop() -> None:
    """pytest.skip when this process is in Session 0 (or session id unknown on NT SYSTEM)."""
    import pytest

    if os.name != "nt":
        pytest.skip("windows")
    sid = current_windows_session_id()
    if sid == 0:
        pytest.skip(SESSION0_SKIP_REASON)
    user = (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip().lower()
    # Session id can be None if ProcessIdToSessionId fails; SYSTEM without a
    # session name is still not an interactive desktop.
    if sid is None and user in ("system", "local service", "network service"):
        pytest.skip(SESSION0_SKIP_REASON)
