#!/usr/bin/env python3
"""Live IRC host for airc console service (FR #253).

ChanServ-registered ``#{machinename}`` → nick ``{machinename}_console``.
Otherwise lobby on ``#{domain_or_workgroup}`` as ``{machinename}`` / ``_N``.
Silent in channel; authenticated PRIVMSG → per-user console pipe (NSSM).
"""
from __future__ import annotations

import argparse
import base64
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# t773u: in the split repo checkout the shared modules (account_map ...) live in <repo>/common/scripts; a staged/installed tree is flat.
_common = Path(__file__).resolve().parent.parent.parent / "common" / "scripts"
if _common.is_dir():
    sys.path.insert(1, str(_common))

from account_map import AccountMap, account_from_tags, parse_message_tags, parse_prefix_nick
from airc_console import (
    IRC_SAFE_PAYLOAD,
    AircConsoleCore,
    AuthPolicy,
    ConsoleSessionManager,
    ShellJobRunner,
    chunk_irc_text,
    console_nick,
    domain_channel,
    domain_lobby_nick,
    domain_or_workgroup_id,
    ensure_nickserv_password,
    home_dir,
    load_operators,
    machine_console_nick,
    machine_id,
    parse_chanserv_info,
    resolve_powershell,
    resolve_server_password,
    shop_channel,
)
from airc_jobs import JobProtocol, JobStore, VerbAuthPolicy

FLOOD_S = 0.35
# Issue #298: half-open / silent link detection + reconnect.
IDLE_PING_S = 60.0
IDLE_DEAD_S = 120.0
RECONNECT_MIN_S = 3.0
RECONNECT_MAX_S = 60.0
CHANSERV_PROBE_S = 8.0
NICK_RETRIES_SHOP = 5
NICK_RETRIES_LOBBY = 20


_KEEPALIVE_LOG_INTERVAL_S = 3600.0
_last_keepalive_log_mono = 0.0


def info(msg: str) -> None:
    """ISO-UTC timestamped stdout line; always flush (FR #1546)."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} {msg}", flush=True)


def info_keepalive(msg: str) -> None:
    """Rate-limit keepalive noise to about one line per hour (FR #1546)."""
    global _last_keepalive_log_mono
    import time as _time

    now = _time.monotonic()
    if (now - _last_keepalive_log_mono) < _KEEPALIVE_LOG_INTERVAL_S:
        return
    _last_keepalive_log_mono = now
    info(msg)


def read_password(path: Path | None, env_key: str = "AIRC_CONSOLE_PASSWORD") -> str | None:
    """Legacy helper — prefer resolve_server_password / ensure_nickserv_password (#271)."""
    for key in (env_key, "BOB_IRC_PASSWORD", "AGENTIC_IRC_PASSWORD", "AIRC_CONSOLE_SERVER_PASSWORD"):
        env = os.environ.get(key)
        if env and env.strip():
            return env.strip()
    if path and path.is_file():
        return path.read_text(encoding="utf-8").strip() or None
    return None


class AircConsoleService:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.home = home_dir(args.home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.machine = machine_id(args.machine)
        self.domain = domain_or_workgroup_id(getattr(args, "domain", None))
        self.domain_channel = domain_channel(self.domain)
        self.shop_channel = shop_channel(self.machine)
        # auto | registered | domain-lobby
        mode = (getattr(args, "shop_mode", None) or "auto").strip().lower()
        if mode not in {"auto", "registered", "domain-lobby"}:
            mode = "auto"
        self.shop_mode = mode
        nick_arg = getattr(args, "nick", None)
        self._nick_explicit = bool(
            nick_arg and str(nick_arg).strip() and str(nick_arg).strip().lower() != "auto"
        )
        if self._nick_explicit:
            self.nick = console_nick(self.machine, nick_arg)
        elif self.shop_mode == "domain-lobby":
            self.nick = domain_lobby_nick(self.machine)
        else:
            # Provisional / registered-shop nick.
            self.nick = machine_console_nick(self.machine)
        if self.shop_mode == "domain-lobby":
            self.channel = self.domain_channel
        else:
            self.channel = self.shop_channel
        self._nick_retries = 0
        # #34: nick the SERVER says we hold (001 / own NICK echo), not local intent.
        self.server_nick: str | None = None
        self._sasl_failed = False
        self._pending_join_deadline = 0.0
        self._probe_state = "idle"  # idle | waiting | done
        self._probe_deadline = 0.0
        self._awaiting_lobby_nick = False
        self._joined_shop = False
        self._active_mode: str | None = None
        # #271: NickServ GUID in console.password (mint+reuse). Ergo PASS separate.
        nickserv_path = (
            Path(args.password_file)
            if args.password_file
            else (self.home / "console.password")
        )
        self.nickserv_password = ensure_nickserv_password(nickserv_path, mint=True)
        self.password = self.nickserv_password  # SASL / identify use NickServ secret
        self.server_password = resolve_server_password(
            home=self.home,
            password_file=Path(args.password_file) if args.password_file else None,
        )
        if self.nickserv_password:
            info(f"INFO nickserv-password file={nickserv_path} (GUID store+reuse)")
        if not getattr(args, "sasl", True) and self.shop_mode != "domain-lobby":
            info(
                f"ERROR --no-sasl with shop-mode={self.shop_mode}: the reserved "
                f"{machine_console_nick(self.machine)} nick needs SASL (Ergo nick reservation); "
                "the console will not be able to hold its nick. Remove --no-sasl."
            )
        if self.server_password:
            info("INFO server PASS available (env/ergo.password)")
        else:
            info("INFO no-server-pass (set AGENTIC_IRC_PASSWORD or ergo.password)")
        info(
            f"INFO domain={self.domain} shop={self.shop_channel} "
            f"lobby={self.domain_channel} shop-mode={self.shop_mode}"
        )
        ops = load_operators(
            Path(args.operators_file) if args.operators_file else self.home / "operators.txt",
            args.operators,
        )
        accts = {x.strip().lower() for x in (args.accounts or []) if x.strip()}
        amap = AccountMap()
        amap_path = self.home / "accounts.json"
        amap.load(amap_path)
        self.account_map = amap
        self.amap_path = amap_path
        auth = AuthPolicy(
            operators=ops,
            accounts=accts,
            account_map=amap,
            require_account=bool(args.require_account or accts),
            machine=self.machine,
        )
        if not ops and not accts:
            raise SystemExit("airc console: refuse empty operators/accounts (FR #253)")
        cwd = args.cwd or str(self.home)
        self.sessions = ConsoleSessionManager(
            shell=args.shell or resolve_powershell(),
            cwd=cwd,
            on_output=self._on_console_out,
            idle_sec=float(args.idle_sec),
        )
        self.shell_runner = ShellJobRunner(
            on_reply=self._on_console_out,
            cwd=cwd,
            wait=False,
        )
        # Install root = parent of scripts/ (product tree). Used by FR #77 UPDATE.
        install_root = str(Path(__file__).resolve().parents[1])
        ai_root = Path(os.environ.get("AI_ROOT") or self.home.parent.parent)
        # Verb matrix: empty write/exec sets => any base-authenticated nick (documented).
        self.job_store = JobStore(self.home)
        self.job_protocol = JobProtocol(
            self.job_store,
            verb_auth=VerbAuthPolicy(),
            on_reply=self._on_console_out,
            ai_root=ai_root if (ai_root / "bob").is_dir() or (ai_root / "airc").is_dir() else Path(r"C:\ai"),
            machine=self.machine,
            airc_running=True,
        )
        self.core = AircConsoleCore(
            machine=self.machine,
            auth=auth,
            sessions=self.sessions,
            nick=self.nick,
            shell_runner=self.shell_runner,
            install_root=install_root,
            job_protocol=self.job_protocol,
        )
        self.core.channel = self.channel
        self.sock: ssl.SSLSocket | socket.socket | None = None
        self._send_lock = threading.Lock()
        self._stop = threading.Event()
        self._registered = False
        self._last_recv = 0.0
        self._last_ping_sent = 0.0
        self._awaiting_pong = False
        self._force_reconnect = False

    def _on_console_out(self, nick: str, line: str) -> None:
        # Reply in Query only — never on shop channel (silent).
        # FR #75: chunk deterministically within IRC_SAFE_PAYLOAD (no silent 400 clip).
        text = (line or "").replace("\n", " ").replace("\r", " ")
        for piece in chunk_irc_text(text, limit=IRC_SAFE_PAYLOAD, prefix=""):
            self.send_privmsg(nick, piece)

    def connect(self) -> None:
        self._registered = False
        self._force_reconnect = False
        self._awaiting_pong = False
        raw = socket.create_connection((self.args.host, int(self.args.port)), timeout=30)
        if self.args.tls:
            ctx = ssl.create_default_context()
            if self.args.tls_insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self.sock = ctx.wrap_socket(raw, server_hostname=self.args.host)
        else:
            self.sock = raw
        self.sock.settimeout(1.0)
        self._last_recv = time.monotonic()
        info(f"INFO connected {self.args.host}:{self.args.port} tls={self.args.tls}")

    def send(self, line: str) -> None:
        if not self.sock:
            raise ConnectionError("send: no socket")
        data = (line.rstrip("\r\n") + "\r\n").encode("utf-8", errors="replace")
        with self._send_lock:
            try:
                self.sock.sendall(data)
            except OSError as e:
                raise ConnectionError(f"send failed: {e}") from e
            time.sleep(FLOOD_S)

    def send_privmsg(self, target: str, text: str) -> None:
        if self.core.may_speak_on_channel() is False and target.lower() == self.channel.lower():
            info(f"INFO drop channel speak target={target}")
            return
        # IRC line length safety
        safe = text.replace("\n", " ").replace("\r", " ")
        self.send(f"PRIVMSG {target} :{safe}")

    def send_notice(self, target: str, text: str) -> None:
        """NOTICE — used for ping replies (including channel ping → Query-style NOTICE)."""
        safe = text.replace("\n", " ").replace("\r", " ")
        self.send(f"NOTICE {target} :{safe}")

    def send_server_pass(self) -> None:
        """Ergo irc.ntsa.uk requires PASS before NICK/USER (same as irc_agent)."""
        if not self.server_password:
            info("INFO no-server-pass (set AGENTIC_IRC_PASSWORD / ergo.password)")
            return
        self.send("PASS " + self.server_password)
        info("INFO sent server PASS")

    def request_caps(self) -> None:
        # account-tag powers operator account allowlists (FR #230). SASL is best-effort.
        caps = "account-notify extended-join account-tag"
        if self.nickserv_password and self.args.sasl:
            caps = "sasl " + caps
            self._want_sasl = True
        else:
            self._want_sasl = False
        self.send(f"CAP REQ :{caps}")

    def sasl_plain(self) -> None:
        if not self.nickserv_password or not self.args.sasl:
            return
        # Minimal PLAIN; failures must CAP END so registration can proceed.
        self._want_sasl = True

    def register_or_identify(self) -> None:
        """Best-effort NickServ identify/register with stored GUID (#271)."""
        if not self.nickserv_password:
            info("INFO skip nick register/identify (no nickserv password)")
            return
        if not self._may_register_nick():
            info(
                f"ERROR refusing NickServ REGISTER/IDENTIFY for {self.nick}: in shop mode the "
                f"console may only own {machine_console_nick(self.machine)} (#34)"
            )
            return
        # Ergo may have services disabled; ignore failures in read loop.
        self.send(f"PRIVMSG NickServ :IDENTIFY {self.nick} {self.nickserv_password}")
        self.send(
            f"PRIVMSG NickServ :REGISTER {self.nickserv_password} console@{self.machine}.local"
        )

    def _may_register_nick(self) -> bool:
        """#34: never auto-register {machine}_N accounts in registered-shop mode."""
        if self._nick_explicit or self.shop_mode == "domain-lobby":
            return True
        if self._active_mode == "domain-lobby":
            return True
        return self.nick.lower() == machine_console_nick(self.machine).lower()

    def handshake(self) -> None:
        self._want_sasl = False
        self._sasl_done = False
        self._probe_state = "idle"
        self._awaiting_lobby_nick = False
        self._joined_shop = False
        self._active_mode = None
        self.server_nick = None
        self._sasl_failed = False
        self._pending_join_deadline = 0.0
        self.core.nick = self.nick
        # Order matches irc_agent: PASS → CAP → NICK/USER → (SASL) → CAP END.
        self.send_server_pass()
        self.request_caps()
        for cmd in self.core.register_commands():
            self.send(cmd)
        if self._want_sasl:
            self.sasl_plain()
        else:
            self.send("CAP END")
        # NickServ for provisional nick; re-run after lobby nick settles.
        self.register_or_identify()

    def _set_nick(self, nick: str) -> None:
        self.nick = nick
        self.core.nick = nick
        self.send(f"NICK {nick}")

    def _holds_nick(self) -> bool:
        """True when the server confirmed we hold self.nick (registered mode only)."""
        if self._active_mode != "registered":
            return True  # lobby keeps the optimistic path (#321)
        return bool(self.server_nick) and self.server_nick.lower() == self.nick.lower()

    def join_shop(self) -> None:
        if not self._holds_nick():
            info(
                f"ERROR not joining {self.channel}: wanted nick {self.nick} but the server "
                f"says we are {self.server_nick or '?'} (#34); deferring until the NICK is confirmed"
            )
            self._pending_join_deadline = time.monotonic() + 10.0
            return
        self._pending_join_deadline = 0.0
        self.core.channel = self.channel
        for cmd in self.core.join_commands():
            self.send(cmd)
        self._joined_shop = True
        info(f"INFO joined {self.channel} as {self.nick} (silent)")

    def _start_chanserv_probe(self) -> None:
        self._probe_state = "waiting"
        self._probe_deadline = time.monotonic() + CHANSERV_PROBE_S
        info(f"INFO chanserv-probe {self.shop_channel}")
        self.send(f"PRIVMSG ChanServ :INFO {self.shop_channel}")

    def _apply_shop_mode(self, mode: str) -> None:
        """Settle registered shop vs domain lobby after ChanServ probe (or forced mode)."""
        if self._probe_state == "done" and self._active_mode == mode and self._joined_shop:
            return
        self._probe_state = "done"
        self._active_mode = mode
        if mode == "registered":
            self.channel = self.shop_channel
            self.core.channel = self.channel
            if not self._nick_explicit:
                want = machine_console_nick(self.machine)
                if self.nick.lower() != want.lower():
                    self._set_nick(want)
            info(f"INFO shop-mode=registered channel={self.channel} nick={self.nick}")
            self.register_or_identify()
            if not self._joined_shop:
                self.join_shop()
            return

        # domain-lobby
        self.channel = self.domain_channel
        self.core.channel = self.channel
        if not self._nick_explicit:
            want = domain_lobby_nick(self.machine)
            if self.nick.lower() != want.lower():
                self._nick_retries = 0
                info(
                    f"INFO shop-mode=domain-lobby channel={self.channel} "
                    f"nick={want} (changing from {self.nick})"
                )
                # Issue #321: do not wait for a NICK echo — Ergo may omit it and
                # we would never JOIN. Optimistic NICK then register+JOIN; 433
                # handler re-nicks and re-JOINs.
                self._set_nick(want)
        info(f"INFO shop-mode=domain-lobby channel={self.channel} nick={self.nick}")
        self.register_or_identify()
        if not self._joined_shop:
            self.join_shop()

    def _finish_lobby_nick(self) -> None:
        """Legacy helper — lobby path no longer blocks on NICK ack (#321)."""
        self._awaiting_lobby_nick = False
        info(f"INFO shop-mode=domain-lobby channel={self.channel} nick={self.nick}")
        self.register_or_identify()
        if not self._joined_shop:
            self.join_shop()

    def _check_probe_timeout(self) -> None:
        if (
            self._pending_join_deadline
            and not self._joined_shop
            and time.monotonic() >= self._pending_join_deadline
        ):
            info(
                f"ERROR nick {self.nick} was never confirmed by the server "
                f"(server says {self.server_nick or '?'}); reconnecting instead of joining under the wrong nick"
            )
            self._pending_join_deadline = 0.0
            self._force_reconnect = True
            return
        if self._probe_state != "waiting":
            return
        if time.monotonic() < self._probe_deadline:
            return
        info("INFO chanserv-probe timeout -> domain-lobby")
        self._apply_shop_mode("domain-lobby")

    def _handle_sasl_line(self, cmd: str, args: list[str], trailing: str) -> None:
        tokens = [a.lower() for a in args] + ([trailing.lower()] if trailing else [])
        if cmd == "CAP" and "ack" in tokens and "sasl" in " ".join(tokens) and self.nickserv_password:
            tok = base64.b64encode(
                f"{self.nick}\0{self.nick}\0{self.nickserv_password}".encode()
            ).decode("ascii")
            self.send("AUTHENTICATE PLAIN")
            self.send(f"AUTHENTICATE {tok}")
            return
        if cmd == "CAP" and "ack" in tokens and not self._want_sasl:
            self.send("CAP END")
            return
        if cmd == "903":
            self._sasl_done = True
            self.send("CAP END")
            return
        if cmd in {"904", "905", "906", "907"}:
            self._sasl_failed = True
            info(
                f"ERROR console account {self.nick} SASL failed ({cmd}): password mismatch "
                f"with console.password, or the account is not registered yet. Reset it "
                f"(NickServ SAPASSWD) or fix console.password; continuing so registration can finish"
            )
            self.send("CAP END")
            return

    def on_line(self, line: str) -> None:
        self._last_recv = time.monotonic()
        tags, rest = parse_message_tags(line)
        if rest.startswith("PING "):
            self.send("PONG " + rest[5:])
            return
        parts = rest.split(" ", 2)
        prefix = ""
        if rest.startswith(":"):
            try:
                prefix, rest2 = rest[1:].split(" ", 1)
            except ValueError:
                return
            rest = rest2
        bits = rest.split(" ")
        cmd = bits[0].upper() if bits else ""
        args = bits[1:]
        trailing = ""
        if " :" in rest:
            _, trailing = rest.split(" :", 1)
            args = rest.split(" :", 1)[0].split(" ")[1:]

        if cmd == "ERROR":
            info(f"INFO server-ERROR {trailing or ' '.join(args)}")
            self._force_reconnect = True
            return

        if cmd == "PONG":
            self._awaiting_pong = False
            return

        if cmd in {"CAP", "AUTHENTICATE", "903", "904", "905", "906", "907"} or (
            cmd == "CAP"
        ):
            self._handle_sasl_line(cmd, args, trailing)

        if cmd == "001":
            # Welcome — probe ChanServ (or forced mode) before JOIN.
            self._registered = True
            self._nick_retries = 0
            self.server_nick = args[0] if args else None
            if self._nick_explicit:
                # Explicit nick: join current channel (shop unless domain-lobby forced).
                self._apply_shop_mode(
                    "domain-lobby" if self.shop_mode == "domain-lobby" else "registered"
                )
            elif self.shop_mode == "registered":
                self._apply_shop_mode("registered")
            elif self.shop_mode == "domain-lobby":
                self._apply_shop_mode("domain-lobby")
            else:
                self._start_chanserv_probe()

        if cmd == "433":
            # Nickname already in use — never get 001/JOIN without recovery.
            self._nick_retries += 1
            lobby = self._active_mode == "domain-lobby" or self.shop_mode == "domain-lobby"
            limit = NICK_RETRIES_LOBBY if lobby else NICK_RETRIES_SHOP
            if self._nick_retries > limit:
                info(f"INFO nick-collision giving up on {self.nick}")
                self._force_reconnect = True
                return
            if lobby:
                alt = domain_lobby_nick(self.machine, self._nick_retries)
            else:
                # #34: shop mode never falls back to {machine}_N. The reserved console
                # nick is only usable by a SASL-authenticated session; fail loudly.
                base = machine_console_nick(self.machine)
                if base.lower() == self.nick.lower() or self._nick_explicit:
                    info(
                        f"ERROR nick {self.nick} refused (433, reserved by NickServ). "
                        f"{'SASL failed for this account; ' if self._sasl_failed else ''}"
                        f"NOT falling back to {self.machine}_N. Fix the account password "
                        f"(console.password) and restart the Airc service."
                    )
                    self._force_reconnect = True
                    return
                alt = base
            info(f"INFO nick-in-use 433 {self.nick} -> {alt}")
            self._set_nick(alt)
            if lobby and self._active_mode == "domain-lobby":
                # Re-IDENTIFY and re-JOIN under the collision nick (#321).
                self.register_or_identify()
                self._joined_shop = False
                self.join_shop()
            return

        if cmd == "NICK":
            # Optional echo; lobby no longer depends on it (#321).
            new_nick = (trailing or (args[0] if args else "")).lstrip(":")
            old_nick = (parse_prefix_nick(":" + prefix) if prefix else "") or ""
            if (
                new_nick
                and self.server_nick
                and old_nick.lower() == self.server_nick.lower()
            ):
                self.server_nick = new_nick  # #34: our own rename was confirmed
            if new_nick and self.nick and new_nick.lower() == self.nick.lower():
                self._awaiting_lobby_nick = False
                if (
                    self._active_mode == "registered"
                    and not self._joined_shop
                    and self._pending_join_deadline
                    and self._holds_nick()
                ):
                    self.register_or_identify()
                    self.join_shop()

        if cmd == "NOTICE":
            src = parse_prefix_nick(":" + prefix) if prefix else ""
            src_l = (src or "").lower()
            if self._probe_state == "waiting" and src_l in {"chanserv", "cs"}:
                status = parse_chanserv_info(trailing, self.shop_channel)
                info(f"INFO chanserv-info status={status}")
                if status == "registered":
                    self._apply_shop_mode("registered")
                elif status == "missing":
                    self._apply_shop_mode("domain-lobby")
                # unknown: keep waiting until timeout

        if cmd == "JOIN":
            nick = parse_prefix_nick(":" + prefix) if prefix else None
            # extended-join: JOIN #chan account :gecos
            acct = None
            if len(args) >= 2 and args[1] and not args[1].startswith("#") and args[1] != "*":
                acct = args[1]
            if nick and acct:
                self.account_map.set(nick, acct)
                self.account_map.save(self.amap_path)

        acct_tag = account_from_tags(tags)
        if acct_tag and prefix:
            nick = parse_prefix_nick(":" + prefix) or prefix.split("!")[0]
            self.account_map.set(nick, acct_tag)
            self.account_map.save(self.amap_path)

        hr = self.core.handle_raw(line)
        if not hr:
            return
        if hr.action == "ctcp_pong" and hr.nick is not None:
            # CTCP PONG via NOTICE (standard); works for client /ping flam*
            payload = hr.reply if hr.reply is not None else ""
            body = f"\x01PING {payload}\x01" if payload != "" else "\x01PING\x01"
            self.send_notice(hr.nick, body)
            info(f"INFO ctcp-pong to={hr.nick}")
        elif hr.action == "pong" and hr.nick and hr.reply:
            # Channel or Query "ping flam*" → NOTICE (not channel PRIVMSG).
            self.send_notice(hr.nick, hr.reply)
            info(f"INFO pong to={hr.nick} {hr.reply}")
        elif hr.action == "deny" and hr.nick and hr.reply:
            self.send_privmsg(hr.nick, hr.reply)
        elif hr.action in {"help", "close", "update"} and hr.nick and hr.reply:
            # FR #77: UPDATE reply is sent before the detached helper stops Airc.
            self.send_privmsg(hr.nick, hr.reply)
            if hr.action == "update":
                info(f"INFO update-reply to={hr.nick} {hr.reply}")
        elif hr.action == "shell":
            info(f"INFO shell from={hr.nick}")
        elif hr.action == "job":
            info(f"INFO job from={hr.nick}")
        elif hr.action == "pipe":
            info(f"INFO pipe from={hr.nick}")

    def _idle_keepalive(self) -> None:
        """Detect half-open links: client PING, then force reconnect if no traffic (#298)."""
        now = time.monotonic()
        idle = now - self._last_recv
        if self._awaiting_pong and (now - self._last_ping_sent) >= IDLE_DEAD_S:
            info("INFO idle-dead (no PONG/traffic); reconnecting")
            self._force_reconnect = True
            return
        if self._registered and idle >= IDLE_PING_S and not self._awaiting_pong:
            token = str(int(time.time()))
            try:
                self.send(f"PING :{token}")
            except ConnectionError as e:
                info(f"INFO keepalive-send-err {e}")
                self._force_reconnect = True
                return
            self._last_ping_sent = now
            self._awaiting_pong = True
            info_keepalive("INFO keepalive PING sent")

    def read_loop(self) -> None:
        assert self.sock is not None
        buf = b""
        while not self._stop.is_set() and not self._force_reconnect:
            try:
                chunk = self.sock.recv(4096)
            except (socket.timeout, TimeoutError):
                # Python 3.10+ ssl may raise TimeoutError; keep the loop alive (#286).
                try:
                    self._check_probe_timeout()
                except Exception as pe:
                    info(f"INFO probe-err {pe}")
                try:
                    self.sessions.reap_idle()
                except Exception as re:
                    info(f"INFO reap-err {re}")
                try:
                    self._idle_keepalive()
                except Exception as ke:
                    info(f"INFO keepalive-err {ke}")
                    self._force_reconnect = True
                continue
            except Exception as e:
                info(f"INFO recv-err {e}")
                break
            if not chunk:
                info("INFO eof")
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if line:
                    try:
                        self.on_line(line)
                    except ConnectionError as e:
                        info(f"INFO on_line-conn-err {e}")
                        self._force_reconnect = True
                        break
                    except Exception as e:
                        info(f"INFO on_line-err {e}")
            if self._force_reconnect:
                break

    def run(self) -> int:
        info(f"INFO airc-console machine={self.machine} channel={self.channel} nick={self.nick}")
        if not self.server_password:
            info(
                "ERROR no-server-pass: set ConsoleHome/ergo.password or AGENTIC_IRC_PASSWORD. "
                "irc.ntsa.uk requires PASS; without it TLS ends EOF and the console never registers."
            )
            return 2
        backoff = RECONNECT_MIN_S
        while not self._stop.is_set():
            session_ok = False
            try:
                self.connect()
                self.handshake()
                self.read_loop()
                session_ok = self._registered
            except Exception as e:
                info(f"INFO session-err {e}")
            finally:
                self.sessions.close_all()
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
            if self._stop.is_set():
                break
            if session_ok:
                backoff = RECONNECT_MIN_S
            info(f"INFO reconnect in {backoff:.0f}s (registered={session_ok})")
            time.sleep(backoff)
            backoff = min(RECONNECT_MAX_S, max(RECONNECT_MIN_S, backoff * 2))
        return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="airc console Windows service host (FR #253)")
    p.add_argument("--host", default=os.environ.get("AIRC_IRC_HOST", "irc.ntsa.uk"))
    p.add_argument("--port", type=int, default=int(os.environ.get("AIRC_IRC_PORT", "6697")))
    p.add_argument("--tls", action="store_true", default=True)
    p.add_argument("--no-tls", action="store_false", dest="tls")
    p.add_argument("--tls-insecure", action="store_true")
    p.add_argument(
        "--nick",
        default="auto",
        help="IRC nick (default auto = {machine}_console provisional; lobby uses {machine}/_{n})",
    )
    p.add_argument(
        "--machine",
        default=None,
        help="fleet shop id (ionos/flamingo/…); default AIRC_CONSOLE_MACHINE / BOB_MACHINE_ID / COMPUTERNAME",
    )
    p.add_argument(
        "--domain",
        default=None,
        help="domain/workgroup id for lobby channel; default AIRC_CONSOLE_DOMAIN / Windows join",
    )
    p.add_argument(
        "--shop-mode",
        default=os.environ.get("AIRC_CONSOLE_SHOP_MODE", "auto"),
        choices=["auto", "registered", "domain-lobby"],
        help="auto=ChanServ INFO #{machine}; registered=#{machine} as {machine}_console; "
        "domain-lobby=#{domain} as {machine}",
    )
    p.add_argument("--home", default=None)
    p.add_argument("--password-file", default=None)
    p.add_argument(
        "--sasl",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="SASL PLAIN after server PASS (default on; required for reserved "
        "{machine}_console nick). Use --no-sasl only on lab nets without NickServ.",
    )
    p.add_argument("--operators", nargs="*", default=[])
    p.add_argument("--operators-file", default=None)
    p.add_argument("--accounts", nargs="*", default=[], help="services account allowlist")
    p.add_argument("--require-account", action="store_true")
    p.add_argument("--shell", default=None)
    p.add_argument("--cwd", default=None)
    p.add_argument("--idle-sec", type=float, default=3600.0)
    p.add_argument("--selftest", action="store_true", help="offline smoke then exit 0")
    return p


def selftest() -> int:
    mid = machine_id("IONOS")
    assert shop_channel(mid) == "#ionos", shop_channel(mid)
    assert machine_console_nick("IONOS") == "ionos_console"
    assert console_nick("IONOS") == "ionos_console"
    assert console_nick("IONOS", "auto") == "ionos_console"
    assert console_nick("IONOS", "console") == "console"
    assert domain_lobby_nick("IONOS") == "ionos"
    assert domain_lobby_nick("IONOS", 1) == "ionos_1"
    assert domain_channel("CE-PRIORITY-DEV") == "#ce-priority-dev"
    assert parse_chanserv_info("Channel #ionos is not registered.", "#ionos") == "missing"
    assert (
        parse_chanserv_info("Information on channel #ionos:\nRegistered: yes", "#ionos")
        == "registered"
    )
    assert parse_chanserv_info("Channel #marchhare is registered", "#marchhare") == "registered"
    assert parse_chanserv_info("Registered at: Tue, 29 Sep 2026 17:50:35 UTC", "#marchhare") == "registered"
    auth = AuthPolicy(operators={"simon"}, accounts=set())
    assert auth.allow("Simon")
    assert not auth.allow("stranger")
    core = AircConsoleCore(
        machine="ionos", auth=auth, sessions=ConsoleSessionManager(on_output=None), nick="ionos_console"
    )
    assert core.may_speak_on_channel() is False
    r = core.handle_raw(":evil!e@h PRIVMSG #ionos :whoami")
    assert r and r.action == "silent_channel"
    r2 = core.handle_raw(":evil!e@h PRIVMSG ionos_console :whoami")
    assert r2 and r2.action == "deny"
    assert isinstance(is_frozen_airc_exe(), bool)
    _ = resolve_airc_install_root()  # must not raise
    info("INFO selftest ok")
    return 0


def is_frozen_airc_exe() -> bool:
    """True when running as PyInstaller airc.exe (FR #2397 / #2401)."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def resolve_airc_install_root() -> Path | None:
    """Install tree root for Sync/Update scripts (``<ai root>\\airc``)."""
    if is_frozen_airc_exe():
        exe = Path(sys.executable).resolve()
        # Pack stages ``airc\\airc.exe`` under the install root.
        if exe.parent.name.lower() == "airc":
            return exe.parent.parent
        return exe.parent
    here = Path(__file__).resolve().parent
    # Source: ``airc/scripts`` -> ``airc``; staged flat: ``scripts`` -> install root.
    if here.name.lower() == "scripts":
        return here.parent
    return here


def _resolve_powershell() -> str | None:
    found = shutil.which("powershell.exe")
    if found:
        return found
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidate = Path(windir) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _run_ps1_best_effort(script: Path, args: list[str], label: str) -> None:
    """Run a pack script; never raise (service start must continue). FR #2401."""
    ps = _resolve_powershell()
    if not ps:
        info(f"WARN {label}: powershell.exe missing")
        return
    if not script.is_file():
        info(f"WARN {label}: missing {script}")
        return
    cmd = [
        ps,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *args,
    ]
    try:
        # Check mode of Update-BobiverseService always exits 0 and is bounded;
        # Sync is ff-only and must not block the start on failure.
        subprocess.run(
            cmd,
            cwd=str(script.parent),
            timeout=120,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:  # noqa: BLE001 - start path must never abort
        info(f"WARN {label}: {exc}")


def kick_frozen_service_start_hooks() -> None:
    """Parity with Start-AircConsole -ServiceMode when NSSM runs airc.exe (FR #2401).

    Legacy powershell + Start-AircConsole.ps1 already runs Sync/Update before Python;
    only the frozen exe path needs this (otherwise we would double-check every start).
    Opt-outs: BOBIVERSE_NO_UPDATE=1 skips both; BOB_AUTOUPDATE=0 / autoupdate.disabled
    are honoured inside Update-BobiverseService.ps1.
    """
    if not is_frozen_airc_exe():
        return
    root = resolve_airc_install_root()
    if root is None:
        return
    scripts = root / "scripts"
    no_update = (os.environ.get("BOBIVERSE_NO_UPDATE") or "").strip() == "1"
    if not no_update:
        sync = scripts / "Sync-BobiverseFromRepo.ps1"
        if sync.is_file():
            try:
                info(f"INFO frozen sync-from-repo InstallRoot={root}")
                _run_ps1_best_effort(
                    sync,
                    ["-Product", "airc", "-InstallRoot", str(root)],
                    "sync-from-repo",
                )
            except Exception as exc:  # noqa: BLE001
                info(f"WARN sync-from-repo: {exc}")
        updater = scripts / "Update-BobiverseService.ps1"
        if updater.is_file():
            try:
                info("INFO frozen self-update check (Update-BobiverseService)")
                _run_ps1_best_effort(
                    updater,
                    [
                        "-Product",
                        "airc",
                        "-InstallRoot",
                        str(root),
                        "-ServiceName",
                        "Airc",
                    ],
                    "self-update",
                )
            except Exception as exc:  # noqa: BLE001
                info(f"WARN self-update: {exc}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.selftest:
        return selftest()
    # FR #2401: airc.exe NSSM Application skips Start-AircConsole.ps1; restore S4 hooks.
    kick_frozen_service_start_hooks()
    return AircConsoleService(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
