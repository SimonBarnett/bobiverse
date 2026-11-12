"""FR #6441: AD/CredMan auth + sessions for Jeeves appliance settings.

Off by default: importing this module never starts a server. Child FR #6440
wires these helpers into the LAN HTTP listener. Never log or return passwords.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable

import jeeves_settings as js

CREDMAN_TARGET = "Jeeves/ApplianceAdmin"
SESSION_STORE = "appliance-sessions.json"
SESSION_TTL_S = 8 * 60 * 60.0  # 8h
SESSION_BYTES = 32

Authenticator = Callable[[str, str, str], bool]
CredReader = Callable[[str], dict[str, str]]


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def session_path(home: Path) -> Path:
    return Path(home) / SESSION_STORE


def load_sessions(home: Path) -> dict[str, Any]:
    path = session_path(home)
    if not path.is_file():
        return {"sessions": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return {"sessions": {}}
    if not isinstance(raw, dict):
        return {"sessions": {}}
    sessions = raw.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
    return {"sessions": sessions}


def save_sessions(home: Path, doc: dict[str, Any]) -> None:
    path = session_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    sessions = doc.get("sessions") if isinstance(doc.get("sessions"), dict) else {}
    # Never persist plaintext passwords or raw tokens.
    clean: dict[str, Any] = {}
    for k, v in sessions.items():
        if not isinstance(v, dict):
            continue
        clean[str(k)] = {
            "actor": str(v.get("actor") or "")[:80],
            "exp": float(v.get("exp") or 0),
            "created": float(v.get("created") or 0),
        }
    blob = {"v": 1, "sessions": clean}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(blob, indent=2, sort_keys=True) + chr(10), encoding="utf-8")
    os.replace(tmp, path)


def read_credman_generic(target: str) -> dict[str, str]:
    """Read CredMan generic credential for *target*. Never log the password.

    Uses Win32 CredRead via ctypes (no PowerShell). Returns {} when missing.
    """
    t = (target or "").strip()
    if not t:
        return {}
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return {}

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    CredReadW = advapi32.CredReadW
    CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    CredReadW.restype = wintypes.BOOL
    CredFree = advapi32.CredFree
    CredFree.argtypes = [ctypes.c_void_p]
    CredFree.restype = None

    ptr = ctypes.c_void_p()
    # CRED_TYPE_GENERIC = 1
    if not CredReadW(t, 1, 0, ctypes.byref(ptr)) or not ptr.value:
        return {}
    try:
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
        user = cred.UserName or ""
        pw = ""
        if cred.CredentialBlob and cred.CredentialBlobSize:
            pw = ctypes.wstring_at(cred.CredentialBlob, cred.CredentialBlobSize // 2)
        if not user and not pw:
            return {}
        return {"username": user, "password": pw}
    except Exception:
        return {}
    finally:
        CredFree(ptr)


def authenticate_credman(
    username: str,
    password: str,
    *,
    cred_reader: CredReader | None = None,
    target: str = CREDMAN_TARGET,
) -> bool:
    """True when username+password match the CredMan generic credential."""
    reader = cred_reader or read_credman_generic
    try:
        cred = reader(target) or {}
    except Exception:
        return False
    if not isinstance(cred, dict):
        return False
    expect_user = str(cred.get("username") or "").strip()
    expect_pw = str(cred.get("password") or "")
    if not expect_user or not expect_pw:
        return False
    got_user = str(username or "").strip().lower()
    got_pw = str(password or "")
    # compare_digest requires equal length; length mismatch is a hard fail.
    user_ok = len(got_user) == len(expect_user.lower()) and hmac.compare_digest(
        expect_user.lower(), got_user
    )
    pw_ok = len(got_pw) == len(expect_pw) and hmac.compare_digest(expect_pw, got_pw)
    return bool(user_ok and pw_ok)


def split_windows_account(username: str, domain: str = "") -> tuple[str, str, str]:
    """Split DOMAIN\\user or user@domain. JSON domain used when username has no split.

    Returns (sam, domain, typed_string).
    """
    typed = str(username or "").strip()
    json_dom = str(domain or "").strip()
    user = typed
    dom = json_dom
    if typed and "@" in typed and "\\" not in typed.split("@", 1)[0]:
        left, _, right = typed.partition("@")
        user = left.strip()
        if right.strip():
            dom = right.strip()
    elif "\\" in typed:
        left, _, right = typed.partition("\\")
        if right.strip():
            dom = left.strip()
            user = right.strip()
    return user, dom, typed


def _call_logon_user(user: str, domain: str, password: str) -> bool:
    """Win32 LogonUser network logon. Returns False off-Windows / fail."""
    if not str(user or "").strip() or password is None:
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return False
    LOGON32_LOGON_NETWORK = 3
    LOGON32_PROVIDER_DEFAULT = 0
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LogonUserW = advapi32.LogonUserW
    LogonUserW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    LogonUserW.restype = wintypes.BOOL
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL
    handle = wintypes.HANDLE()
    dom = str(domain or "").strip() or None
    ok = LogonUserW(
        str(user).strip(),
        dom,
        str(password),
        LOGON32_LOGON_NETWORK,
        LOGON32_PROVIDER_DEFAULT,
        ctypes.byref(handle),
    )
    if not ok:
        return False
    try:
        return True
    finally:
        if handle:
            CloseHandle(handle)


def authenticate_windows_logon(
    username: str,
    password: str,
    domain: str = "",
) -> bool:
    """Validate via Win32 LogonUser (network logon). Returns False off-Windows / fail."""
    sam, dom, _typed = split_windows_account(username, domain)
    if not sam or password is None:
        return False
    return _call_logon_user(sam, dom, str(password))


def default_authenticator(username: str, password: str, domain: str = "") -> bool:
    """Try Windows/AD LogonUser first; fall back to CredMan ApplianceAdmin.

    CredMan is tried with the typed string and, when split, with the SAM name.
    """
    _sam, _dom, typed = split_windows_account(username, domain)
    if authenticate_windows_logon(username, password, domain=domain):
        return True
    if authenticate_credman(typed, password):
        return True
    if _sam and _sam != typed and authenticate_credman(_sam, password):
        return True
    return False


def login(
    home: Path,
    *,
    client_ip: str,
    username: str,
    password: str,
    domain: str = "",
    authenticator: Authenticator | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Issue a session token after LAN + credential checks. Never returns password."""
    err = js.reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    user = str(username or "").strip()
    if not user:
        return {"ok": False, "error": "unauthorized: missing username"}
    auth_fn = authenticator or default_authenticator
    try:
        ok = bool(auth_fn(user, str(password or ""), str(domain or "")))
    except TypeError:
        # Allow 2-arg test lambdas.
        ok = bool(auth_fn(user, str(password or "")))  # type: ignore[call-arg, misc]
    except Exception:
        ok = False
    if not ok:
        return {"ok": False, "error": "unauthorized: bad credentials"}
    now_f = float(now if now is not None else time.time())
    token = secrets.token_urlsafe(SESSION_BYTES)
    th = _hash_token(token)
    doc = load_sessions(home)
    sessions = doc.setdefault("sessions", {})
    # Drop expired while writing.
    alive = {
        k: v
        for k, v in sessions.items()
        if isinstance(v, dict) and float(v.get("exp") or 0) > now_f
    }
    alive[th] = {
        "actor": user[:80],
        "exp": now_f + float(SESSION_TTL_S),
        "created": now_f,
    }
    doc["sessions"] = alive
    save_sessions(home, doc)
    return {
        "ok": True,
        "session_token": token,
        "actor": user[:80],
        "expires_in": int(SESSION_TTL_S),
    }


def require_session(
    home: Path,
    *,
    client_ip: str,
    session_token: str | None,
    now: float | None = None,
) -> dict[str, Any]:
    """Validate LAN + session. Returns {ok, actor} or {ok:False, error}."""
    err = js.reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    tok = str(session_token or "").strip()
    if not tok:
        return {"ok": False, "error": "unauthorized: missing session"}
    now_f = float(now if now is not None else time.time())
    doc = load_sessions(home)
    sessions = doc.get("sessions") if isinstance(doc.get("sessions"), dict) else {}
    row = sessions.get(_hash_token(tok))
    if not isinstance(row, dict):
        return {"ok": False, "error": "unauthorized: invalid session"}
    try:
        exp = float(row.get("exp") or 0)
    except (TypeError, ValueError):
        exp = 0.0
    if exp <= now_f:
        return {"ok": False, "error": "unauthorized: session expired"}
    actor = str(row.get("actor") or "").strip() or "unknown"
    return {"ok": True, "actor": actor}


def logout(
    home: Path,
    *,
    client_ip: str,
    session_token: str | None,
) -> dict[str, Any]:
    err = js.reject_non_lan(client_ip)
    if err:
        return {"ok": False, "error": err}
    tok = str(session_token or "").strip()
    if not tok:
        return {"ok": True, "revoked": False}
    doc = load_sessions(home)
    sessions = doc.get("sessions") if isinstance(doc.get("sessions"), dict) else {}
    th = _hash_token(tok)
    if th in sessions:
        sessions.pop(th, None)
        doc["sessions"] = sessions
        save_sessions(home, doc)
        return {"ok": True, "revoked": True}
    return {"ok": True, "revoked": False}


def api_get_settings_authed(
    home: Path,
    *,
    client_ip: str,
    session_token: str | None,
) -> dict[str, Any]:
    gate = require_session(home, client_ip=client_ip, session_token=session_token)
    if not gate.get("ok"):
        return {"ok": False, "error": str(gate.get("error") or "unauthorized")}
    return js.api_get_settings(home, client_ip=client_ip)


def api_put_setting_authed(
    home: Path,
    *,
    client_ip: str,
    session_token: str | None,
    key: str,
    value: Any,
    actor: str = "",
) -> dict[str, Any]:
    gate = require_session(home, client_ip=client_ip, session_token=session_token)
    if not gate.get("ok"):
        return {"ok": False, "error": str(gate.get("error") or "unauthorized")}
    session_actor = str(gate.get("actor") or "unknown")
    return js.api_put_setting(
        home,
        client_ip=client_ip,
        key=key,
        value=value,
        actor=session_actor,
    )


def api_rollback_authed(
    home: Path,
    *,
    client_ip: str,
    session_token: str | None,
    backup_id: str,
) -> dict[str, Any]:
    gate = require_session(home, client_ip=client_ip, session_token=session_token)
    if not gate.get("ok"):
        return {"ok": False, "error": str(gate.get("error") or "unauthorized")}
    return js.api_rollback(
        home,
        client_ip=client_ip,
        backup_id=backup_id,
        actor=str(gate.get("actor") or "unknown"),
    )
