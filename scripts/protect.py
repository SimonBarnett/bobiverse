"""File ACL (Windows icacls / Unix 0600) and identity-at-rest (DPAPI on NT)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAGIC = b"AIRC1"
MAGIC_MACHINE = b"AIRC2"  # DPAPI CRYPTPROTECT_LOCAL_MACHINE: readable by any account on THIS box (file ACL guards it)


class ProtectError(Exception):
    pass


def protect_path(path: Path) -> None:
    path = Path(path)
    if os.name == "nt":
        # Medium-IL / UAC-filtered tokens do not get BUILTIN\Administrators ACEs
        # ("group used for deny only"). Grant DOMAIN\USER with (OI)(CI) so mkdir
        # of children works after /inheritance:r. (Haitch join 2026-09-24)
        user = os.environ.get("USERNAME") or "Administrators"
        domain = (os.environ.get("USERDOMAIN") or "").strip()
        if domain and domain.upper() not in ("", ".", "UNKNOWN"):
            user_spec = f"{domain}\\{user}"
        else:
            user_spec = user
        # Also grant local machine account when domain-joined (bob homes carry both).
        # Skip MACHINE$ / LocalSystem-as-USERNAME (icacls 1332 — issue #3).
        machine = (os.environ.get("COMPUTERNAME") or "").strip()
        grants = [
            "NT AUTHORITY\\SYSTEM:(OI)(CI)(F)",
            "BUILTIN\\Administrators:(OI)(CI)(F)",
        ]
        user_l = (user or "").rstrip("$")
        if user and not user.endswith("$") and user.upper() not in ("SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE"):
            grants.append(f"{user_spec}:(OI)(CI)(F)")
            if machine and domain and machine.upper() != domain.upper() and user_l:
                grants.append(f"{machine}\\{user}:(OI)(CI)(F)")
        if path.is_file():
            # (OI)(CI) on a FILE yields an EMPTY DACL after /inheritance:r (file unreadable,
            # even by its owner) - found while provisioning config\oper.cred. Plain (F) for files.
            grants = [g.replace("(OI)(CI)", "") for g in grants]
        cmd = ["icacls", str(path), "/inheritance:r"]
        for g in grants:
            cmd.extend(["/grant:r", g])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stderr or r.stdout or f"icacls exit {r.returncode}").strip()
            # Soft-fail under LocalSystem when profile ACL mapping fails; home under C:\ai\*\home is OK.
            if "1332" in err or "No mapping between account names" in err:
                sys.stderr.write(f"WARN protect_path soft-fail: {err}\n")
                return
            sys.stderr.write(err + "\n")
            raise ProtectError(f"icacls exit {r.returncode}")
        return
    try:
        os.chmod(path, 0o600 if path.is_file() else 0o700)
    except OSError as e:
        raise ProtectError(f"chmod failed: {e}") from e


def _dpapi_protect(data: bytes, machine: bool = False) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 4 if machine else 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def write_secret_bytes(path: Path, data: bytes, machine: bool = False) -> None:
    """DPAPI-protect ``data`` at rest (Windows). ``machine=True`` binds to the machine, not the
    user, so an installer run by one account can provision a secret a service account reads."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path.write_bytes((MAGIC_MACHINE if machine else MAGIC) + _dpapi_protect(data, machine))
    else:
        path.write_bytes(data)
    protect_path(path)


def read_secret_bytes(path: Path) -> bytes:
    raw = Path(path).read_bytes()
    if raw.startswith(MAGIC):
        return _dpapi_unprotect(raw[len(MAGIC) :])
    if raw.startswith(MAGIC_MACHINE):
        return _dpapi_unprotect(raw[len(MAGIC_MACHINE) :])
    return raw


if sys.platform == "win32":
    pass
