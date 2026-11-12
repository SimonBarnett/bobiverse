"""Detect a Windows interactive desktop vs Session 0 / headless sid>0.

FR #6729: flamingo !build runs pytest as ircBob (LocalSystem, Session 0).
That window station has no visible ConsoleWindowClass and no usable user
clipboard. Tests that EnumWindows a visible console, or that exercise the
real OpenClipboard / CONIN$ path, must skip with a durable reason instead of
failing the release suite.

FR #6733: redqueen (and similar) can report sid>0 with USERNAME set but
SESSIONNAME empty and EnumWindows still cannot see a ConsoleWindowClass for a
fresh CREATE_NEW_CONSOLE child (Cursor/agent seat / no usable desktop). Skip
those seats; do not treat empty SESSIONNAME alone as proof (interactive seats
often omit SESSIONNAME while OpenInputDesktop + EnumWindows still work).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import time
from ctypes import wintypes

SESSION0_SKIP_REASON = (
    "FR #6729: Session 0 (non-interactive / isolated SYSTEM suite) cannot host "
    "clipboard or visible console UI"
)

HEADLESS_SID_SKIP_REASON = (
    "FR #6733: no usable interactive desktop for EnumWindows "
    "(sid>0 headless / empty SESSIONNAME agent seat; ConsoleWindowClass not visible)"
)

CREATE_NEW_CONSOLE = 0x00000010
DESKTOP_READOBJECTS = 0x0001


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


def session_name() -> str:
    """Return SESSIONNAME stripped, or empty when unset/blank."""
    return (os.environ.get("SESSIONNAME") or "").strip()


def open_input_desktop_ok() -> bool:
    """True when OpenInputDesktop succeeds (interactive window station present)."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        h = user32.OpenInputDesktop(0, False, DESKTOP_READOBJECTS)
        if not h:
            return False
        try:
            user32.CloseDesktop(h)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _visible_console_count_for_pid(pid: int) -> int:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    count = ctypes.c_int(0)

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):  # noqa: N802 - WinAPI callback
        proc = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc))
        if int(proc.value) != int(pid):
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value == "ConsoleWindowClass":
            count.value += 1
        return True

    user32.EnumWindows(_enum, 0)
    return int(count.value)


def can_enum_visible_console_window(*, timeout_s: float = 2.0) -> bool:
    """Cheap probe: CREATE_NEW_CONSOLE cmd child visible to EnumWindows.

    FR #6733: empty SESSIONNAME alone is not enough (interactive agent seats
    often omit it). If OpenInputDesktop fails, or a short-lived visible console
    never appears to EnumWindows, the hidden-tray UI test cannot pass.
    """
    if os.name != "nt":
        return False
    if not open_input_desktop_ok():
        return False
    cmd = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cmd.exe")
    if not os.path.isfile(cmd):
        return False
    proc = None
    try:
        proc = subprocess.Popen(
            [cmd, "/d", "/c", "ping -n 6 127.0.0.1 >nul"],
            creationflags=CREATE_NEW_CONSOLE,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        deadline = time.monotonic() + max(0.5, float(timeout_s))
        while time.monotonic() < deadline:
            if _visible_console_count_for_pid(proc.pid) >= 1:
                return True
            time.sleep(0.1)
        return False
    except Exception:
        return False
    finally:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass


def skip_unless_interactive_desktop() -> None:
    """pytest.skip when Session 0 or EnumWindows cannot see a visible console."""
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
    # FR #6733: sid>0 but no usable EnumWindows desktop (incl. empty SESSIONNAME
    # agent seats where Create+Enum fails).
    if not can_enum_visible_console_window():
        pytest.skip(HEADLESS_SID_SKIP_REASON)
