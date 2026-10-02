"""Minimal TLS IRC session for ghost QUIT and NAMES probes (no logging of secrets)."""
from __future__ import annotations

import socket
import ssl
import time
from typing import Callable

LineHandler = Callable[[str], list[str]]


def _connect(host: str, port: int, server_hostname: str | None = None) -> ssl.SSLSocket:
    ctx = ssl.create_default_context()
    raw = socket.create_connection((host, port), 20)
    raw.settimeout(2.0)
    sock = ctx.wrap_socket(raw, server_hostname=server_hostname or host)
    return sock


def _send(sock: ssl.SSLSocket, line: str) -> None:
    sock.sendall((line + "\r\n").encode("utf-8"))


def _drain(
    sock: ssl.SSLSocket,
    deadline: float,
    on_line: LineHandler | None = None,
) -> list[str]:
    buf = b""
    seen: list[str] = []
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
        except (TimeoutError, OSError):
            if on_line:
                for reply in on_line(""):
                    _send(sock, reply)
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            text = line.decode("utf-8", "replace").rstrip("\r")
            seen.append(text)
            if on_line:
                for reply in on_line(text):
                    _send(sock, reply)
    return seen


def _auto_pong(line: str) -> list[str]:
    if line.startswith("PING "):
        return ["PONG " + line[5:]]
    return []


def ghost_quit_session(
    host: str,
    port: int,
    nick: str,
    password: str,
    *,
    wait_registered_s: float = 25.0,
    wait_quit_s: float = 3.0,
) -> bool:
    """Connect as nick, send QUIT, close. True if QUIT was sent after 001."""
    sock = _connect(host, port)
    registered = False
    quit_sent = False

    def on_line(line: str) -> list[str]:
        nonlocal registered, quit_sent
        out = _auto_pong(line)
        if line.startswith(":") and " 001 " in line:
            registered = True
            out.append("QUIT :ghost-prune")
            quit_sent = True
        return out

    try:
        if password:
            _send(sock, "PASS " + password)
        _send(sock, "CAP END")
        _send(sock, "NICK " + nick)
        _send(sock, f"USER {nick} 0 * :ghost-quit")
        _drain(sock, time.time() + wait_registered_s, on_line)
        if registered and not quit_sent:
            _send(sock, "QUIT :ghost-prune")
            quit_sent = True
        _drain(sock, time.time() + wait_quit_s, _auto_pong)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return quit_sent


def names_includes_nick(
    host: str,
    port: int,
    observer_nick: str,
    password: str,
    channel: str,
    target: str,
) -> bool:
    """True if NAMES listing for channel includes target nick (case-insensitive)."""
    sock = _connect(host, port)
    names_blob = ""
    target_l = target.lower()

    def on_line(line: str) -> list[str]:
        nonlocal names_blob
        if " 353 " in line or " NAMES " in line:
            names_blob += " " + line
        out = _auto_pong(line)
        if line.startswith(":") and " 001 " in line:
            out.append("NAMES " + channel)
        return out

    try:
        if password:
            _send(sock, "PASS " + password)
        _send(sock, "CAP END")
        _send(sock, "NICK " + observer_nick)
        _send(sock, f"USER {observer_nick} 0 * :names-probe")
        _drain(sock, time.time() + 20.0, on_line)
    finally:
        try:
            sock.close()
        except OSError:
            pass
    blob_l = names_blob.lower()
    return f" {target_l} " in blob_l or f":{target_l} " in blob_l
