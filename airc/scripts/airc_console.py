#!/usr/bin/env python3
"""airc console service core (FR #253).

Installable Windows service: on ChanServ-registered ``#{machinename}`` sit as
``{machinename}_console``; otherwise lobby on ``#{domain_or_workgroup}`` as
``{machinename}`` / ``{machinename}_N``. Silent in channel. Authenticated
PRIVMSG sessions get a per-user console pipe.

Offline-testable: auth, channel naming, session lifecycle, silent policy.
Live IRC loop lives in ``airc_console_service.py``.
"""
from __future__ import annotations

import base64
import binascii
import fnmatch
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from account_map import AccountMap, parse_message_tags

NICK = "console"
IRC_NICK_MAX = 30
# Legacy interactive default (cmd). FR #75 default oneshot shell is PowerShell 5.1.
DEFAULT_SHELL = os.environ.get("COMSPEC") or "cmd.exe"
IRC_SAFE_PAYLOAD = 350
PSB64_MAX_CHARS = 24_000
SHELL_OUTPUT_MAX_BYTES = 64_000
SHELL_TIMEOUT_S = 120.0
_PRIVMSG_RE = re.compile(
    r"^:([^!\s]+)(?:![^@\s]*@\S+)?\s+PRIVMSG\s+(\S+)\s+:?(.*)$",
    re.IGNORECASE,
)
_CHANNEL_SAFE = re.compile(r"[^A-Za-z0-9_-]+")
_CTCP_PING_RE = re.compile(r"^\x01PING(?: (.*))?\x01\s*$", re.IGNORECASE | re.DOTALL)
_PING_CMD_RE = re.compile(r"^\s*ping(?:\s+(\S+))?\s*$", re.IGNORECASE)
# Issue #302: fleet ear nicks bob-{machine} are already authenticated; machine varies.
_BOB_FLEET_NICK_RE = re.compile(r"^bob-[a-z0-9][a-z0-9_-]*$", re.IGNORECASE)

ShopProbeResult = Literal["registered", "missing", "unknown"]


def _sanitize_id(raw: str) -> str:
    cleaned = _CHANNEL_SAFE.sub("-", (raw or "").strip()).strip("-_")
    return (cleaned or "unknown").lower()


def machine_id(override: str | None = None) -> str:
    """Fleet shop id for ``#{machine}`` / ``{machine}_console``.

    Prefer explicit override, then ``AIRC_CONSOLE_MACHINE`` / ``BOB_MACHINE_ID``
    (fleet ids like ``ionos``), then Windows ``COMPUTERNAME``. Using bare
    COMPUTERNAME alone (e.g. ``WIN-MPRE8VI4U6U``) joins the wrong channel and
    looks like \"does not connect\" on ``#ionos`` / ``#flamingo``.
    """
    raw = (
        override
        or os.environ.get("AIRC_CONSOLE_MACHINE")
        or os.environ.get("BOB_MACHINE_ID")
        or os.environ.get("COMPUTERNAME")
        or os.environ.get("HOSTNAME")
        or "unknown"
    ).strip()
    return _sanitize_id(raw)


def shop_channel(machine: str | None = None) -> str:
    mid = machine_id(machine)
    return f"#{mid}"


def _fit_nick(stem: str, suffix: str = "") -> str:
    """Build an IRC nick <= IRC_NICK_MAX, preferring to keep ``suffix`` intact."""
    stem = (stem or "unknown").strip("-_") or "unknown"
    suffix = suffix or ""
    max_stem = IRC_NICK_MAX - len(suffix)
    if max_stem < 1:
        return (stem + suffix)[:IRC_NICK_MAX]
    return (stem[:max_stem] + suffix)[:IRC_NICK_MAX]


def machine_console_nick(machine: str | None = None) -> str:
    """Nick when ``#{machine}`` is ChanServ-registered: ``{machine}_console``."""
    mid = machine_id(machine)
    return _fit_nick(mid, "_console")


def domain_lobby_nick(machine: str | None = None, suffix: int | None = None) -> str:
    """Nick for domain/workgroup lobby: ``{machine}`` or ``{machine}_{n}`` (n>=1)."""
    mid = machine_id(machine)
    if suffix is None or int(suffix) <= 0:
        return _fit_nick(mid, "")
    return _fit_nick(mid, f"_{int(suffix)}")


def console_nick(machine: str | None = None, explicit: str | None = None) -> str:
    """IRC nick for the console seat.

    Default is ``{machine}_console`` (registered-shop / provisional connect).
    Pass explicit ``console`` only on a single-console network; ``auto`` uses default.
    """
    if explicit and explicit.strip() and explicit.strip().lower() != "auto":
        return explicit.strip()[:IRC_NICK_MAX]
    return machine_console_nick(machine)


def domain_or_workgroup_id(override: str | None = None) -> str:
    """Windows domain NetBIOS name, or workgroup, sanitized for ``#{id}``.

    Order: explicit / ``AIRC_CONSOLE_DOMAIN`` → ``USERDNSDOMAIN`` first label →
    ``USERDOMAIN`` when it differs from ``COMPUTERNAME`` → short NetGetJoinInformation
    probe → ``USERDOMAIN`` → ``workgroup``. Never blocks unbounded on WMI.
    """
    if override and override.strip():
        return _sanitize_id(override)
    env = (os.environ.get("AIRC_CONSOLE_DOMAIN") or "").strip()
    if env:
        return _sanitize_id(env)

    dns = (os.environ.get("USERDNSDOMAIN") or "").strip()
    if dns:
        return _sanitize_id(dns.split(".")[0])

    userdomain = (os.environ.get("USERDOMAIN") or "").strip()
    computer = (os.environ.get("COMPUTERNAME") or "").strip()
    if userdomain and computer and userdomain.upper() != computer.upper():
        return _sanitize_id(userdomain)

    joined = _net_get_join_id(timeout_s=2.0)
    if joined:
        return joined

    if userdomain:
        return _sanitize_id(userdomain)
    return "workgroup"


def domain_channel(domain: str | None = None) -> str:
    return f"#{domain_or_workgroup_id(domain)}"


def _net_get_join_id(timeout_s: float = 2.0) -> str | None:
    """Best-effort NetGetJoinInformation (domain or workgroup name)."""
    if os.name != "nt":
        return None
    box: dict[str, str | None] = {"name": None}

    def worker() -> None:
        try:
            import ctypes
            from ctypes import wintypes

            netapi = ctypes.WinDLL("netapi32")
            NetGetJoinInformation = netapi.NetGetJoinInformation
            NetGetJoinInformation.argtypes = [
                wintypes.LPCWSTR,
                ctypes.POINTER(wintypes.LPWSTR),
                ctypes.POINTER(ctypes.c_int),
            ]
            NetGetJoinInformation.restype = wintypes.DWORD
            NetApiBufferFree = netapi.NetApiBufferFree
            NetApiBufferFree.argtypes = [wintypes.LPVOID]
            NetApiBufferFree.restype = wintypes.DWORD

            buf = wintypes.LPWSTR()
            join_type = ctypes.c_int()
            # NetSetupUnknownStatus=0, Workgroup=1, Domain=3 (values vary by SDK;
            # we only need the name string).
            rc = NetGetJoinInformation(None, ctypes.byref(buf), ctypes.byref(join_type))
            if rc == 0 and buf.value:
                box["name"] = str(buf.value)
            if buf:
                NetApiBufferFree(buf)
        except Exception:
            return

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout_s)
    if box["name"]:
        return _sanitize_id(box["name"])
    return None


def parse_chanserv_info(text: str, channel: str) -> ShopProbeResult:
    """Classify a ChanServ INFO NOTICE for ``channel``.

    Returns ``registered``, ``missing``, or ``unknown`` (keep waiting / treat as
    missing after probe timeout).
    """
    body = (text or "").strip()
    if not body:
        return "unknown"
    t = body.lower()
    ch = (channel or "").lower().lstrip("#")
    if any(
        s in t
        for s in (
            "is not registered",
            "isn't registered",
            "isnt registered",
            "not registered",
        )
    ):
        return "missing"
    if "no such channel" in t and ch and ch in t.replace("#", ""):
        return "missing"
    # Atheme / Ergo-style success. Ergo: "Channel #foo is registered" (no colon).
    if "registered:" in t or "registered on" in t or "registered at" in t:
        return "registered"
    if "is registered" in t:
        return "registered"
    if "information on" in t and ch and ch in t.replace("#", ""):
        return "registered"
    if "founder:" in t and ch and ch in t.replace("#", ""):
        return "registered"
    return "unknown"


def is_channel_target(target: str) -> bool:
    t = (target or "").strip()
    return bool(t) and t[0] in "#&+"


def nick_matches_pattern(pattern: str, nick: str, machine: str | None = None) -> bool:
    """True if IRC/client ping pattern matches this console (#298).

    Examples: ``*``, ``flam*``, ``flamingo_console``, ``flamingo``, ``flamingo_1``.
    """
    pat = (pattern or "").strip()
    if not pat or pat == "*":
        return True
    n = (nick or "").strip().lower()
    mid = machine_id(machine)
    candidates = {
        n,
        mid,
        f"console-{mid}",
        f"{mid}_console",
        machine_console_nick(mid),
        domain_lobby_nick(mid),
        f"#{mid}",
    }
    p = pat.lower()
    # Allow #channel-style patterns too.
    for c in candidates:
        if not c:
            continue
        if fnmatch.fnmatchcase(c, p) or fnmatch.fnmatchcase(c.lstrip("#"), p.lstrip("#")):
            return True
        # Prefix match without wildcard: "flam" matches flamingo / flamingo_console
        if "*" not in p and "?" not in p and (c.startswith(p) or c.lstrip("#").startswith(p)):
            return True
    return False


def parse_ctcp_ping(text: str) -> str | None:
    """Return CTCP PING payload (possibly empty string) or None if not CTCP PING."""
    m = _CTCP_PING_RE.match(text or "")
    if not m:
        return None
    return m.group(1) if m.group(1) is not None else ""


def parse_ping_command(text: str) -> str | None:
    """Return ping pattern (``*`` if bare ``ping``) or None if not a ping command."""
    m = _PING_CMD_RE.match(text or "")
    if not m:
        return None
    return (m.group(1) or "*").strip()


def is_bob_fleet_nick(nick: str) -> bool:
    """True for fleet ear nicks ``bob-{machinename}`` (issue #302)."""
    return bool(_BOB_FLEET_NICK_RE.match((nick or "").strip()))


@dataclass
class AuthPolicy:
    """Only authenticated operators may drive the console via PRIVMSG."""

    operators: set[str] = field(default_factory=set)
    accounts: set[str] = field(default_factory=set)
    account_map: AccountMap | None = None
    require_account: bool = False
    # When set, also allow bob-<machine> for this box; bob-* fleet nicks always allowed (#302).
    machine: str | None = None

    def allow(self, nick: str, account: str | None = None) -> bool:
        n = (nick or "").strip().lower()
        if not n:
            return False
        # Fleet bob-{machine} seats are already authenticated on Ergo (#302).
        if is_bob_fleet_nick(n):
            return True
        ops = {x.lower() for x in self.operators}
        mid = machine_id(self.machine) if self.machine is not None else None
        if mid:
            ops.add(f"bob-{mid}")
        accts = {x.lower() for x in self.accounts}
        if self.account_map is not None and account is None:
            account = self.account_map.get(n)
        acct = (account or "").strip().lower()
        need_acct = self.require_account or bool(accts)
        if need_acct:
            if not acct or acct == "*":
                return False
            if accts and acct not in accts:
                return False
        if ops:
            return n in ops
        return need_acct


class ShellRequestError(ValueError):
    """Malformed or oversized console shell request (FR #75)."""


ShellKind = Literal["ps", "cmd", "psb64"]


@dataclass
class ShellRequest:
    kind: ShellKind
    body: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class ShellOutcome:
    job_id: str
    exit_code: int
    stdout: str
    stderr: str


def resolve_powershell() -> str:
    """Windows PowerShell 5.1 host (not pwsh) unless AIRC_POWERSHELL overrides."""
    env = (os.environ.get("AIRC_POWERSHELL") or "").strip()
    if env:
        return env
    found = shutil.which("powershell.exe") or shutil.which("powershell")
    return found or "powershell.exe"


def resolve_comspec() -> str:
    return (os.environ.get("COMSPEC") or "").strip() or "cmd.exe"


def encode_ps_encoded_command(script: str) -> str:
    """Base64 of UTF-16LE script text for ``powershell -EncodedCommand``."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _looks_like_utf16le_script(raw: bytes) -> bool:
    """True when bytes look like UTF-16LE (ASCII-heavy scripts have 0x00 on odd indexes)."""
    if len(raw) < 2 or len(raw) % 2:
        return False
    zeros = sum(1 for i in range(1, len(raw), 2) if raw[i] == 0)
    return zeros >= max(1, len(raw) // 4)


def prepare_psb64_encoded_command(payload: str) -> str:
    """Decode ``psb64:`` payload to an ``-EncodedCommand`` ASCII base64 string.

    Rules (FR #75): prefer native UTF-16LE EncodedCommand bytes when the payload
    looks like UTF-16LE; otherwise treat decoded bytes as UTF-8 script text and
    re-encode to UTF-16LE for ``-EncodedCommand``.
    """
    text = (payload or "").strip()
    if not text:
        raise ShellRequestError("malformed psb64: empty")
    if len(text) > PSB64_MAX_CHARS:
        raise ShellRequestError("psb64 too large")
    try:
        raw = base64.b64decode(text, validate=True)
    except binascii.Error as exc:
        raise ShellRequestError("malformed psb64") from exc
    if _looks_like_utf16le_script(raw):
        try:
            raw.decode("utf-16-le")
            return base64.b64encode(raw).decode("ascii")
        except UnicodeDecodeError:
            pass
    try:
        script = raw.decode("utf-8")
        return encode_ps_encoded_command(script)
    except UnicodeDecodeError:
        pass
    if len(raw) % 2 == 0:
        try:
            raw.decode("utf-16-le")
            return base64.b64encode(raw).decode("ascii")
        except UnicodeDecodeError as exc:
            raise ShellRequestError("malformed psb64") from exc
    raise ShellRequestError("malformed psb64")


def parse_shell_request(text: str) -> ShellRequest:
    """Parse a console PRIVMSG into ps / cmd: / psb64: (FR #75)."""
    raw = (text or "").strip()
    if not raw:
        raise ShellRequestError("empty command")
    low = raw.lower()
    if low.startswith("psb64:"):
        payload = raw[6:]
        # Validate early; body stores original payload for argv build.
        prepare_psb64_encoded_command(payload)
        return ShellRequest(kind="psb64", body=payload)
    if low.startswith("cmd:"):
        body = raw[4:].lstrip()
        if not body:
            raise ShellRequestError("empty cmd:")
        return ShellRequest(kind="cmd", body=body)
    return ShellRequest(kind="ps", body=raw)


def build_shell_argv(req: ShellRequest) -> list[str]:
    if req.kind == "cmd":
        return [resolve_comspec(), "/d", "/c", req.body]
    if req.kind == "psb64":
        enc = prepare_psb64_encoded_command(req.body)
    else:
        enc = encode_ps_encoded_command(req.body)
    return [
        resolve_powershell(),
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        enc,
    ]


def _clip_bytes(data: bytes, limit: int = SHELL_OUTPUT_MAX_BYTES) -> tuple[str, bool]:
    clipped = len(data) > limit
    chunk = data[:limit]
    return chunk.decode("utf-8", errors="replace"), clipped


def run_shell_request(
    req: ShellRequest,
    *,
    timeout_s: float = SHELL_TIMEOUT_S,
    cwd: str | None = None,
) -> ShellOutcome:
    argv = build_shell_argv(req)
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            cwd=cwd,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out, _ = _clip_bytes(exc.stdout or b"")
        err, _ = _clip_bytes(exc.stderr or b"")
        err = (err + ("\n" if err else "") + f"timeout after {timeout_s:.0f}s").strip()
        return ShellOutcome(job_id=req.job_id, exit_code=124, stdout=out, stderr=err)
    out, out_clip = _clip_bytes(proc.stdout or b"")
    err, err_clip = _clip_bytes(proc.stderr or b"")
    if out_clip:
        out += "\n[clipped stdout]"
    if err_clip:
        err += "\n[clipped stderr]"
    return ShellOutcome(
        job_id=req.job_id,
        exit_code=int(proc.returncode),
        stdout=out,
        stderr=err,
    )


def chunk_irc_text(text: str, *, limit: int = IRC_SAFE_PAYLOAD, prefix: str = "") -> list[str]:
    """Split ``text`` so each ``prefix + chunk`` fits ``limit`` (IRC-safe)."""
    room = max(8, limit - len(prefix))
    raw = text.replace("\r", "").replace("\n", " ")
    if not raw:
        return [prefix] if prefix else [""]
    return [prefix + raw[i : i + room] for i in range(0, len(raw), room)]


def format_shell_replies(
    outcome: ShellOutcome,
    *,
    irc_limit: int = IRC_SAFE_PAYLOAD,
) -> list[str]:
    """Stable output contract: ordered out/err seq lines + terminal DONE (FR #75)."""
    lines: list[str] = []
    seq = 0

    def emit(stream: str, label: str) -> None:
        nonlocal seq
        parts = stream.splitlines() if stream else []
        if stream and not parts:
            parts = [""]
        for part in parts:
            # Reserve prefix room using a provisional seq width, then emit.
            body = part
            while True:
                seq += 1
                prefix = f"{label} id={outcome.job_id} seq={seq} "
                room = max(8, irc_limit - len(prefix))
                piece, body = body[:room], body[room:]
                lines.append(prefix + piece)
                if not body:
                    break

    emit(outcome.stdout, "out")
    emit(outcome.stderr, "err")
    lines.append(f"DONE id={outcome.job_id} exit={outcome.exit_code}")
    return lines


class ShellJobRunner:
    """Run one FR #75 shell request; emit reply lines to the operator Query."""

    def __init__(
        self,
        *,
        on_reply: Callable[[str, str], None] | None = None,
        cwd: str | None = None,
        timeout_s: float = SHELL_TIMEOUT_S,
        wait: bool = False,
    ) -> None:
        self.on_reply = on_reply
        self.cwd = cwd
        self.timeout_s = timeout_s
        self.wait = wait
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def start(self, nick: str, command: str) -> str:
        key = nick.strip().lower()

        def worker() -> None:
            try:
                try:
                    req = parse_shell_request(command)
                except ShellRequestError as exc:
                    jid = uuid.uuid4().hex[:8]
                    self._emit(key, f"err id={jid} seq=1 {exc}")
                    self._emit(key, f"DONE id={jid} exit=2")
                    return
                outcome = run_shell_request(req, timeout_s=self.timeout_s, cwd=self.cwd)
                for line in format_shell_replies(outcome):
                    self._emit(key, line)
            finally:
                with self._lock:
                    self._threads.pop(key, None)

        t = threading.Thread(target=worker, name=f"airc-shell-{key}", daemon=True)
        with self._lock:
            self._threads[key] = t
        t.start()
        if self.wait:
            t.join(timeout=self.timeout_s + 5)
        return key

    def _emit(self, nick: str, line: str) -> None:
        if self.on_reply:
            self.on_reply(nick, line)

    def close_nick(self, nick: str) -> None:
        # Oneshoot threads are daemon; nothing durable to kill beyond tracking.
        with self._lock:
            self._threads.pop(nick.strip().lower(), None)


@dataclass
class ConsoleSession:
    nick: str
    proc: subprocess.Popen[str]
    created_at: float = field(default_factory=time.time)
    last_at: float = field(default_factory=time.time)

    def write_line(self, text: str) -> None:
        self.last_at = time.time()
        if self.proc.stdin is None:
            raise RuntimeError("console stdin closed")
        self.proc.stdin.write(text + "\n")
        self.proc.stdin.flush()

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.alive():
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=2)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass


class ConsoleSessionManager:
    """One interactive shell per authenticated nick."""

    def __init__(
        self,
        *,
        shell: str | None = None,
        cwd: str | None = None,
        on_output: Callable[[str, str], None] | None = None,
        idle_sec: float = 3600.0,
    ) -> None:
        self.shell = shell or DEFAULT_SHELL
        self.cwd = cwd
        self.on_output = on_output
        self.idle_sec = idle_sec
        self._lock = threading.Lock()
        self._sessions: dict[str, ConsoleSession] = {}

    def get_or_create(self, nick: str) -> ConsoleSession:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.get(key)
            if sess and sess.alive():
                sess.last_at = time.time()
                return sess
            if sess:
                sess.close()
            proc = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=self.cwd,
                bufsize=1,
            )
            sess = ConsoleSession(nick=key, proc=proc)
            self._sessions[key] = sess
            if self.on_output and proc.stdout is not None:
                threading.Thread(
                    target=self._pump,
                    args=(key, proc),
                    name=f"airc-console-{key}",
                    daemon=True,
                ).start()
            return sess

    def _pump(self, nick: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                text = line.rstrip("\r\n")
                if self.on_output:
                    self.on_output(nick, text)
        except Exception:
            pass

    def pipe(self, nick: str, command: str) -> ConsoleSession:
        sess = self.get_or_create(nick)
        sess.write_line(command)
        return sess

    def close_nick(self, nick: str) -> None:
        key = nick.strip().lower()
        with self._lock:
            sess = self._sessions.pop(key, None)
        if sess:
            sess.close()

    def close_all(self) -> None:
        with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
        for _, sess in items:
            sess.close()

    def reap_idle(self, now: float | None = None) -> int:
        now = time.time() if now is None else now
        dead: list[str] = []
        with self._lock:
            for k, sess in list(self._sessions.items()):
                if (not sess.alive()) or (now - sess.last_at > self.idle_sec):
                    dead.append(k)
            for k in dead:
                sess = self._sessions.pop(k, None)
                if sess:
                    sess.close()
        return len(dead)

    def active(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions.keys())


@dataclass
class HandleResult:
    action: str
    nick: str | None = None
    target: str | None = None
    text: str | None = None
    reply: str | None = None


class AircConsoleCore:
    """Pure handler: parse PRIVMSG, gate auth, run shell jobs, stay silent on channel."""

    def __init__(
        self,
        *,
        machine: str | None = None,
        auth: AuthPolicy,
        sessions: ConsoleSessionManager | None = None,
        nick: str = NICK,
        shell_runner: ShellJobRunner | None = None,
    ) -> None:
        self.machine = machine_id(machine)
        self.channel = shop_channel(self.machine)
        self.auth = auth
        self.nick = nick
        self.sessions = sessions or ConsoleSessionManager()
        self.shell_runner = shell_runner
        self.channel_traffic: list[str] = []

    def register_commands(self) -> list[str]:
        """NickServ register / identify sequence (password from env/file at service layer)."""
        return [
            f"NICK {self.nick}",
            f"USER {self.nick} 0 * :airc console service",
        ]

    def join_commands(self) -> list[str]:
        # Ergo creates channel on first JOIN when permitted; silent — no PRIVMSG.
        return [f"JOIN {self.channel}"]

    def may_speak_on_channel(self) -> bool:
        return False

    def handle_raw(self, line: str) -> HandleResult | None:
        tags, rest = parse_message_tags(line.rstrip("\r\n"))
        m = _PRIVMSG_RE.match(rest)
        if not m:
            return None
        nick, target, text = m.group(1), m.group(2), m.group(3)
        account = tags.get("account")
        if self.auth.account_map is not None and account:
            self.auth.account_map.set(nick, account)

        # Issue #298: CTCP PING / "ping [pattern]" — no operator auth; presence only.
        ctcp_payload = parse_ctcp_ping(text or "")
        if ctcp_payload is not None:
            return HandleResult(
                action="ctcp_pong",
                nick=nick,
                target=target,
                text=text,
                reply=ctcp_payload,
            )
        ping_pat = parse_ping_command(text or "")
        if ping_pat is not None:
            if nick_matches_pattern(ping_pat, self.nick, self.machine):
                return HandleResult(
                    action="pong",
                    nick=nick,
                    target=target,
                    text=text,
                    reply=f"pong {self.nick}",
                )
            if is_channel_target(target):
                self.channel_traffic.append(text)
                return HandleResult(action="silent_channel", nick=nick, target=target, text=text)
            # Direct ping that does not match us — ignore quietly.
            return HandleResult(action="ping_miss", nick=nick, target=target, text=text)

        if is_channel_target(target):
            # Silent in channel: ignore public traffic (do not reply on channel).
            self.channel_traffic.append(text)
            return HandleResult(action="silent_channel", nick=nick, target=target, text=text)

        # Direct PRIVMSG to console nick
        if not self.auth.allow(nick, account):
            return HandleResult(
                action="deny",
                nick=nick,
                target=target,
                text=text,
                reply="denied: authenticate / not an operator",
            )

        cmd = (text or "").strip()
        if not cmd:
            return HandleResult(action="empty", nick=nick, target=target, text=text)
        if cmd.lower() in {".quit", "!quit", "exit"}:
            self.sessions.close_nick(nick)
            if self.shell_runner is not None:
                self.shell_runner.close_nick(nick)
            return HandleResult(action="close", nick=nick, target=target, text=text, reply="console closed")
        if cmd.lower() in {".help", "!help"}:
            return HandleResult(
                action="help",
                nick=nick,
                target=target,
                text=text,
                reply=(
                    "airc console (FR #75): default PowerShell -NoProfile; "
                    "cmd: COMSPEC escape; psb64:<base64> EncodedCommand; "
                    "replies out/err id= seq= then DONE id= exit=; "
                    ".quit closes; silent on channel; answers ping"
                ),
            )

        # FR #75: oneshot PowerShell / cmd: / psb64: with DONE framing.
        if self.shell_runner is not None:
            self.shell_runner.start(nick, cmd)
            return HandleResult(action="shell", nick=nick, target=target, text=text)

        # Legacy interactive pipe (tests / AIRC without runner).
        self.sessions.pipe(nick, cmd)
        return HandleResult(action="pipe", nick=nick, target=target, text=text)


def load_operators(path: Path | None, cli: list[str] | None = None) -> set[str]:
    ops: set[str] = set()
    if cli:
        ops.update(x.strip().lstrip("\ufeff") for x in cli if x and x.strip())
    if path and path.is_file():
        # utf-8-sig strips BOM from PowerShell Set-Content -Encoding utf8 (issue #289).
        text = path.read_text(encoding="utf-8-sig")
        for line in text.splitlines():
            s = line.strip().lstrip("\ufeff")
            if not s or s.startswith("#"):
                continue
            ops.add(s)
    return ops


def home_dir(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("AIRC_CONSOLE_HOME")
    if env:
        return Path(env)
    return Path.home() / ".airc-console"


def ensure_nickserv_password(path: Path, *, mint: bool = True) -> str | None:
    """Load or mint the NickServ password (issue #271).

    First start writes a GUID into ``console.password`` and reuses it later.
    This is **not** the Ergo server PASS — that comes from env / ergo.password.
    """
    import uuid

    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    if not mint:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = str(uuid.uuid4())
    path.write_text(secret + "\n", encoding="utf-8")
    try:
        # Best-effort: owner-only on POSIX; Windows ACLs set by install/hotpatch.
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret


def resolve_server_password(
    *,
    home: Path | None = None,
    password_file: Path | None = None,
) -> str | None:
    """Ergo / IRC server PASS — never invent; never use NickServ GUID file alone.

    Order: AIRC_CONSOLE_SERVER_PASSWORD, AGENTIC_IRC_PASSWORD, AIRC_CONSOLE_PASSWORD
    (legacy), then ``ergo.password`` / ``connect.password`` beside home or
    ``~/.grok/ergo/connect.password``. Explicit ``password_file`` is **not** used
    here when it is the NickServ GUID path (``console.password``).
    """
    for key in (
        "AIRC_CONSOLE_SERVER_PASSWORD",
        "BOB_IRC_PASSWORD",
        "AGENTIC_IRC_PASSWORD",
        "AIRC_CONSOLE_PASSWORD",
    ):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    candidates: list[Path] = []
    # Legacy: only treat password_file as server PASS when it is NOT console.password
    if password_file is not None and password_file.name.lower() != "console.password":
        candidates.append(password_file)
    if home is not None:
        candidates.extend(
            [
                home / "ergo.password",
                home / "connect.password",
            ]
        )
    # Fleet default connect.password — only when using the real user console home
    # (avoid leaking ~/.grok secrets into hermetic tests with a tmp home).
    real_home = home_dir()
    if home is None or Path(home).resolve() == real_home.resolve():
        candidates.append(Path.home() / ".grok" / "ergo" / "connect.password")
    for p in candidates:
        try:
            if p.is_file():
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except OSError:
            continue
    return None
