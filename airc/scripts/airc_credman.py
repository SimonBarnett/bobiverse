"""Shared Win32 CredMan helpers for airc (FR #5526 / #5802).

Default path uses CredReadW / CredWriteW via ctypes — no PowerShell / Add-Type
subprocess (that blocked IRC ~30s on missing targets). Never log or raise secrets.
"""
from __future__ import annotations

from dataclasses import dataclass


class CredmanError(Exception):
    """Non-secret CredMan failure. ``reason`` is safe for IRC (no blob/username)."""

    def __init__(self, reason: str) -> None:
        self.reason = str(reason or "credman-error")
        super().__init__(self.reason)


@dataclass(frozen=True)
class CredmanPair:
    username: str
    password: str


ERROR_NOT_FOUND = 1168
CRED_TYPE_GENERIC = 1
# Survive logoff; visible to LocalSystem service (FR #5802 Priority CredMan).
CRED_PERSIST_LOCAL_MACHINE = 2


def read_generic_credential(target: str) -> CredmanPair | None:
    """Read a CRED_TYPE_GENERIC credential.

    Returns ``None`` when the target is missing (Win32 1168).
    Raises ``CredmanError`` with a numeric/platform reason on other failures.
    """
    import os

    if os.name != "nt":
        raise CredmanError("unsupported-platform")

    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    t = (target or "").strip()
    if not t:
        return None

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    cred_read.restype = wintypes.BOOL
    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    ptr = ctypes.c_void_p()
    ok = cred_read(t, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr))
    if not ok or not ptr.value:
        err = int(ctypes.get_last_error() or 0)
        if err == ERROR_NOT_FOUND:
            return None
        raise CredmanError(f"winerror-{err}")

    try:
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIALW)).contents
        user = str(cred.UserName or "")
        pw = ""
        size = int(cred.CredentialBlobSize or 0)
        if cred.CredentialBlob and size > 0:
            even = size - (size % 2)
            raw = ctypes.string_at(cred.CredentialBlob, even)
            pw = raw.decode("utf-16-le", errors="strict")
        return CredmanPair(username=user, password=pw)
    finally:
        cred_free(ptr)


def write_generic_credential(target: str, username: str, password: str) -> None:
    """Write a CRED_TYPE_GENERIC credential (LocalMachine persist).

    FR #5802: used by ``CRED persist`` under the Airc LocalSystem identity.
    Raises ``CredmanError`` with a non-secret reason. Never logs the password.
    """
    import os

    if os.name != "nt":
        raise CredmanError("unsupported-platform")

    import ctypes
    from ctypes import wintypes

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    t = (target or "").strip()
    user = (username or "").strip()
    pw = password or ""
    if not t:
        raise CredmanError("target-empty")
    if not user:
        raise CredmanError("username-empty")
    if not pw:
        raise CredmanError("password-empty")

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    cred_write = advapi32.CredWriteW
    cred_write.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    cred_write.restype = wintypes.BOOL

    blob = pw.encode("utf-16-le")
    blob_buf = ctypes.create_string_buffer(blob)
    cred = CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = t
    cred.Comment = None
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_char))
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.AttributeCount = 0
    cred.Attributes = None
    cred.TargetAlias = None
    cred.UserName = user

    ok = cred_write(ctypes.byref(cred), 0)
    # Best-effort wipe of the temporary blob buffer (password never logged).
    try:
        ctypes.memset(blob_buf, 0, len(blob))
    except Exception:
        pass
    if not ok:
        err = int(ctypes.get_last_error() or 0)
        raise CredmanError(f"winerror-{err}")
