"""FR #8009: classify an airc.exe IRC connect and own the outbound allow rule.

The probe runs inside airc.exe (not PowerShell) because a per-process block
is the failure mode. AIRC_SELFTEST=0 skips the install health step.
"""
from __future__ import annotations

import os
import socket
import ssl
from typing import Callable

RULE_NAME = "airc-exe-outbound-irc"

CLASS_OK = "ok"
CLASS_DNS = "dns"
CLASS_TCP_TIMEOUT = "tcp_timeout"
CLASS_LOCAL_RESET = "local_reset"
CLASS_TLS = "tls"
CLASS_IRC_REFUSAL = "irc_refusal"
CLASS_OTHER = "connect_error"

LOCAL_RESET_TEXT = (
    "local reset: endpoint security or firewall is blocking airc.exe"
)


def _winerror(exc: BaseException) -> int | None:
    for attr in ("winerror", "errno"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    return None


def _is_reset(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionResetError):
        return True
    code = _winerror(exc)
    return code in (10054, 104)


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    code = _winerror(exc)
    return code in (10060, 110)


def classify_connect_error(exc: BaseException, *, bytes_sent: int) -> str:
    """Map a connect/handshake error to a stable class. No host names."""
    if isinstance(exc, socket.gaierror):
        return CLASS_DNS
    if _is_timeout(exc):
        return CLASS_TCP_TIMEOUT
    if _is_reset(exc) and int(bytes_sent) == 0:
        return CLASS_LOCAL_RESET
    if isinstance(exc, ssl.SSLError):
        return CLASS_TLS
    return CLASS_OTHER


def format_class(kind: str, exc: BaseException | None = None, *, host: str = "", port: int = 0) -> str:
    if kind == CLASS_OK:
        return "connect self-test ok"
    if kind == CLASS_DNS:
        return "dns fail"
    if kind == CLASS_TCP_TIMEOUT:
        return "tcp connect timeout (network firewall)"
    if kind == CLASS_LOCAL_RESET:
        return LOCAL_RESET_TEXT
    if kind == CLASS_TLS:
        reason = str(exc or "").strip() or "handshake failed"
        return f"tls error: {reason}"
    if kind == CLASS_IRC_REFUSAL:
        text = str(exc or "").strip() or "refused"
        return f"irc refusal: {text}"
    return f"connect error host={host} port={port}: {exc}"


def filter_outbound_block_rules(show_text: str, exe: str) -> str:
    """Keep enabled outbound Block rules that name this program. Read-only."""
    text = show_text or ""
    if "no rules match" in text.lower():
        return "outbound-block-rules: none"
    blocks = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                blob = "\n".join(current)
                low = blob.lower()
                if "block" in low and (exe.lower() in low or "airc" in low):
                    blocks.append(blob)
            current = []
            continue
        current.append(line)
    if current:
        blob = "\n".join(current)
        low = blob.lower()
        if "block" in low and (exe.lower() in low or "airc" in low):
            blocks.append(blob)
    if not blocks:
        return "outbound-block-rules: none matching program"
    return "outbound-block-rules:\n" + "\n---\n".join(blocks[:8])


def readonly_snapshot(exe: str, runner: Callable[[list[str]], str]) -> str:
    """Best-effort Defender / firewall notes. Never changes those settings."""
    parts = [filter_outbound_block_rules(
        runner(["netsh", "advfirewall", "firewall", "show", "rule", "name=all", "dir=out"]),
        exe,
    )]
    try:
        defender = runner([
            "powershell", "-NoProfile", "-Command",
            "try { $s = Get-MpComputerStatus; "
            "'NetworkProtection=' + [string]$s.IsNetworkProtectionEnabled } "
            "catch { 'defender-unavailable' }",
        ])
    except Exception as exc:
        defender = f"defender-unavailable: {exc}"
    parts.append((defender or "defender-unavailable").strip())
    parts.append("Defender events to check: 1125 1126 1116 1117 (report only).")
    return "\n".join(parts)


def diagnosis_text(exe: str, host: str, port: int, *, snapshot: str = "") -> str:
    """Read-only IT note. Never disables Defender or third-party AV."""
    lines = [
        LOCAL_RESET_TEXT,
        f"program={exe}",
        f"remote={host}:{int(port)} protocol=TCP dir=out",
        "allow rule: "
        f'netsh advfirewall firewall add rule name="{RULE_NAME}" '
        f'dir=out action=allow program="{exe}" protocol=TCP '
        f'remoteip={host} remoteport={int(port)}',
        "Do not disable Defender, Network Protection, Group Policy, or third-party AV.",
        "Report enabled outbound Block rules for this program, "
        "Get-MpComputerStatus Network Protection, and Defender events 1125/1126/1116/1117.",
    ]
    extra = (snapshot or "").strip()
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def allow_rule_add_argv(exe: str, host: str, port: int) -> list[str]:
    return [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={RULE_NAME}",
        "dir=out", "action=allow",
        f"program={exe}",
        "protocol=TCP",
        f"remoteip={host}",
        f"remoteport={int(port)}",
    ]


def allow_rule_show_argv() -> list[str]:
    return ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}"]


def allow_rule_delete_argv() -> list[str]:
    return ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={RULE_NAME}"]


def ensure_allow_rule(exe: str, host: str, port: int, runner: Callable[[list[str]], str]) -> bool:
    """Add the outbound allow rule once. Returns True when this call added it."""
    shown = runner(allow_rule_show_argv()) or ""
    if RULE_NAME.lower() in shown.lower() and "no rules match" not in shown.lower():
        return False
    runner(allow_rule_add_argv(exe, host, port))
    return True


def remove_allow_rule(runner: Callable[[list[str]], str]) -> None:
    runner(allow_rule_delete_argv())


def default_connector(host: str, port: int, timeout: float):
    return socket.create_connection((host, int(port)), timeout=timeout)


def probe_connection(
    host: str,
    port: int,
    *,
    tls: bool,
    connector: Callable[[str, int, float], object] | None = None,
    wrapper: Callable[[object, str], object] | None = None,
    reader: Callable[[object], bytes] | None = None,
    timeout: float = 30.0,
) -> dict:
    """Connect and read one IRC line. Does not send and does not add a firewall rule."""
    if connector is None:
        connector = default_connector
    bytes_sent = 0
    sock = None
    raw = None
    try:
        raw = connector(host, int(port), timeout)
    except OSError as exc:
        kind = classify_connect_error(exc, bytes_sent=0)
        return {"kind": kind, "detail": format_class(kind, exc, host=host, port=port), "bytes_sent": 0}
    try:
        if tls:
            if wrapper is None:
                ctx = ssl.create_default_context()
                sock = ctx.wrap_socket(raw, server_hostname=host)
            else:
                sock = wrapper(raw, host)
        else:
            sock = raw
        if reader is None:
            sock.settimeout(timeout)
            data = b""
            while b"\n" not in data and len(data) < 512:
                chunk = sock.recv(256)
                if not chunk:
                    break
                data += chunk
        else:
            data = reader(sock)
        line = (data or b"").decode("utf-8", errors="replace").strip()
        if not line:
            kind = CLASS_OTHER
            return {
                "kind": kind,
                "detail": "connect error: no IRC line (not a pre-TLS local reset)",
                "bytes_sent": bytes_sent,
            }
        low = line.lower()
        if "closing link" in low or low.startswith("error :") or "banned" in low or "throttl" in low:
            kind = CLASS_IRC_REFUSAL
            return {"kind": kind, "detail": format_class(kind, line, host=host, port=port), "bytes_sent": bytes_sent}
        return {"kind": CLASS_OK, "detail": format_class(CLASS_OK), "bytes_sent": bytes_sent, "line": line}
    except OSError as exc:
        kind = classify_connect_error(exc, bytes_sent=bytes_sent)
        out = {"kind": kind, "detail": format_class(kind, exc, host=host, port=port), "bytes_sent": bytes_sent}
        if kind == CLASS_LOCAL_RESET:
            out["diagnosis"] = diagnosis_text("airc.exe", host, port)
        return out
    finally:
        try:
            if sock is not None:
                sock.close()
            elif raw is not None:
                close = getattr(raw, "close", None)
                if close:
                    close()
        except Exception:
            pass


def selftest_disabled() -> bool:
    return os.environ.get("AIRC_SELFTEST", "1").strip() == "0"
