"""Shared Windows WNet IPC$ helpers (FR #5709 / #5721).

Use WNetAddConnection2W / WNetCancelConnection2W so CredMan passwords stay in
process memory only — never on ``net use`` argv / Event 4688.
"""
from __future__ import annotations


def wnet_add(remote: str, username: str, password: str) -> str:
    """Connect ``remote`` UNC via WNetAddConnection2W.

    Password stays in process memory only. Raises ``OSError`` with ``winerror``
    set to the WNet status (never a blanket remap to 5). Returns ``remote``.
    """
    import ctypes
    from ctypes import wintypes

    class NETRESOURCEW(ctypes.Structure):
        _fields_ = [
            ("dwScope", wintypes.DWORD),
            ("dwType", wintypes.DWORD),
            ("dwDisplayType", wintypes.DWORD),
            ("dwUsage", wintypes.DWORD),
            ("lpLocalName", wintypes.LPWSTR),
            ("lpRemoteName", wintypes.LPWSTR),
            ("lpComment", wintypes.LPWSTR),
            ("lpProvider", wintypes.LPWSTR),
        ]

    unc = (remote or "").strip()
    if not unc:
        raise OSError(87, "wnet-add: empty remote")
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    add = mpr.WNetAddConnection2W
    add.argtypes = [
        ctypes.POINTER(NETRESOURCEW),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
    ]
    add.restype = wintypes.DWORD

    nr = NETRESOURCEW()
    nr.dwType = 0  # RESOURCETYPE_ANY
    nr.lpRemoteName = unc
    user_w = username if username else None
    pass_w = password if password else None
    rc = int(add(ctypes.byref(nr), pass_w, user_w, 0) or 0)
    if rc != 0:
        raise ctypes.WinError(rc)
    return unc


def wnet_add_ipc(host: str, username: str, password: str) -> str:
    """Connect ``\\\\host\\IPC$`` via WNet (FR #5709)."""
    mid = (host or "").strip()
    if not mid:
        raise OSError(87, "wnet-add-ipc: empty host")
    return wnet_add(rf"\\{mid}\IPC$", username, password)


def wnet_cancel(remote: str) -> None:
    """Drop a WNet connection. Never raises secrets; ignore cancel failures."""
    import ctypes
    from ctypes import wintypes

    if not remote:
        return
    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    cancel = mpr.WNetCancelConnection2W
    cancel.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.BOOL]
    cancel.restype = wintypes.DWORD
    cancel(remote, 0, True)


def is_wnet_auth_failed(exc: BaseException) -> bool:
    """True for IPC$/CredMan logon failures (5/86/1326/1385)."""
    win = int(getattr(exc, "winerror", 0) or 0)
    err = int(getattr(exc, "errno", 0) or 0)
    code = win or err
    if code in (5, 86, 1326, 1385):
        return True
    msg = str(exc).lower()
    return (
        "access is denied" in msg
        or "access denied" in msg
        or "logon failure" in msg
        or "bad password" in msg
    )
