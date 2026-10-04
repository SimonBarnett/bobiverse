"""FR #1993: in-process locks + single-instance mutex for jeeves.exe (chair+HTTP).

When the chair and BobCallback share one process, disk ``git-claim.lock`` must not
serialize same-process threads for LOCK_WAIT_S. Enable the in-proc RLock before
starting HTTP + chair. Cross-process tools still use the on-disk lock.
"""
from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path

_INPROC_QUEUE: threading.RLock | None = None
_INPROC_DIGEST: threading.RLock | None = None
_MUTEX_HANDLE = None


def enable_inproc_locks() -> None:
    """Call once from jeeves_main before starting HTTP and chair threads."""
    global _INPROC_QUEUE, _INPROC_DIGEST
    if _INPROC_QUEUE is None:
        _INPROC_QUEUE = threading.RLock()
    if _INPROC_DIGEST is None:
        _INPROC_DIGEST = threading.RLock()


def disable_inproc_locks() -> None:
    """Test helper: restore disk git-claim.lock behaviour."""
    global _INPROC_QUEUE, _INPROC_DIGEST
    _INPROC_QUEUE = None
    _INPROC_DIGEST = None


def inproc_queue_lock() -> threading.RLock | None:
    return _INPROC_QUEUE


def inproc_digest_lock() -> threading.RLock | None:
    return _INPROC_DIGEST


def mutex_name_for_home(home: Path) -> str:
    raw = str(Path(home).expanduser().resolve()).lower().encode("utf-8", errors="replace")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"Global\\BobiverseJeeves-{digest}"


def try_acquire_instance_mutex(home: Path) -> bool:
    """Windows named mutex; True if this process owns the instance. Non-Windows: always True."""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        name = mutex_name_for_home(home)
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), name)
        if not handle:
            return False
        err = kernel32.GetLastError()
        # ERROR_ALREADY_EXISTS = 183
        if err == 183:
            kernel32.CloseHandle(handle)
            return False
        _MUTEX_HANDLE = handle
        return True
    except Exception:  # noqa: BLE001
        return True


def release_instance_mutex() -> None:
    global _MUTEX_HANDLE
    if _MUTEX_HANDLE is None or os.name != "nt":
        _MUTEX_HANDLE = None
        return
    try:
        import ctypes

        ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    _MUTEX_HANDLE = None
