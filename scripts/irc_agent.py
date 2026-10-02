#!/usr/bin/env python3
"""TLS IRC agent: reconnect, SASL from env, flood delay, AGPK TOFU, SEAL v2 inbox.

Stdout is INFO only (no raw IRC, no AGPK/SEAL bodies). Full lines go to irc.log if
BOB_IRC_DEBUG=1. SASL: BOB_IRC_SASL_USER + BOB_IRC_SASL_PASSWORD (not argv).
"""
from __future__ import annotations

import argparse
import base64
import os
import random
import re
import socket
import ssl
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bob_recycle  # noqa: E402
import bobreport  # noqa: E402
import bobstat  # noqa: E402
import bobtalk  # noqa: E402
import gitclaim  # noqa: E402
import focus_ignore  # noqa: E402
import grok_talk  # noqa: E402
import filexfer  # noqa: E402
import moot  # noqa: E402
import protect  # noqa: E402
import seal  # noqa: E402
import shop_ops  # noqa: E402
import shop_chanserv  # noqa: E402
import shop_listen  # noqa: E402
import agent_control  # noqa: E402
import registered_machines  # noqa: E402
import bob_home  # noqa: E402
import chair_oper  # noqa: E402
import chan_privs  # noqa: E402
import chan_workers  # noqa: E402
import talk_seat_ghost  # noqa: E402
import talk_seat_pid  # noqa: E402
import wire  # noqa: E402
import channel_only  # noqa: E402

FLOOD_S = 0.8
# FR #68: cap outbox drain per tick so chair +o / ChanServ sync are not starved
OUTBOX_LINES_PER_TICK = 8
# IRC classic line limit is 512 bytes including CRLF. Ergo rejects oversize relays with 417.
# Safe default for PRIVMSG *text* when LINELEN/prefix unknown (~400 bytes of UTF-8 text).
DEFAULT_PRIVMSG_TEXT_MAX = 400
REG_FAIL_CMDS = frozenset(
    {
        "ERROR",
        "464",
        "465",
        "471",
        "472",
        "473",
        "474",
        "475",
        "477",
        "478",
        "481",
        "482",
        "483",
        "484",
        "485",
        "486",
        "487",
        "488",
        "489",
        "490",
        "491",
        "492",
        "493",
        "494",
        "495",
        "496",
        "497",
        "498",
        "499",
    }
)


_BOM_UTF8 = b"\xef\xbb\xbf"
_BOM_CHAR = "\ufeff"
# Pre-wrapped outbox: optional BOM + PRIVMSG target :body
_PREWRAPPED_PRIVMSG = re.compile(
    r"^\s*PRIVMSG\s+(\S+)\s+:(.*)$",
    re.IGNORECASE | re.DOTALL,
)


def normalize_outbox_line(text: str) -> tuple[str, str]:
    """
    Normalize one outbox line for send (FR #226).

    Returns (kind, line) where kind is:
      - ``privmsg`` — ready ``PRIVMSG target :body`` (no double-wrap)
      - ``bare`` — chat body only (caller may ``say()``)
      - ``empty`` — skip

    Strips leading BOM. If the line is already ``PRIVMSG …``, keeps a single wrap
    (unwraps accidental nested ``PRIVMSG`` in the body once).
    """
    raw = text or ""
    # strip all leading BOMs and spaces (keep trailing body spaces after first non-ws)
    s = raw
    while s.startswith(_BOM_CHAR):
        s = s[1:]
    # lstrip spaces/tabs only at start; BOM may sit after spaces
    lead = 0
    while lead < len(s) and s[lead] in " \t\ufeff":
        lead += 1
    s = s[lead:]
    if not s:
        return "empty", ""

    m = _PREWRAPPED_PRIVMSG.match(s)
    if m:
        target = m.group(1).strip()
        body = m.group(2)
        # Nested wrap: body itself starts with PRIVMSG (double-wrap artifact)
        nested = 0
        while True:
            m2 = _PREWRAPPED_PRIVMSG.match(body.lstrip(" \t\ufeff"))
            if not m2:
                break
            nested += 1
            target = m2.group(1).strip()
            body = m2.group(2)
            if nested > 5:
                break
        if nested:
            info(f"INFO outbox unwrap nested-PRIVMSG x{nested} target={target}")
        # body may still have BOM
        while body.startswith(_BOM_CHAR):
            body = body[1:]
        if not target:
            return "bare", body
        return "privmsg", f"PRIVMSG {target} :{body}"

    # bare message (preferred worker writer form)
    return "bare", s


def write_outbox_line(path: Path, text: str, *, channel: str | None = None) -> None:
    """
    Append one outbox line as UTF-8 **without BOM**.

    Prefer bare message text. If ``channel`` is set, write a single pre-wrapped
    ``PRIVMSG #chan :text`` line (still no BOM). Never writes utf-8-sig.
    """
    body = (text or "").replace("\r", " ").replace("\n", " ")
    # strip accidental BOM from callers
    while body.startswith(_BOM_CHAR):
        body = body[1:]
    body = body.strip("\n\r")
    if channel:
        ch = channel if channel.startswith("#") else f"#{channel}"
        # if caller already passed PRIVMSG, normalize first
        kind, norm = normalize_outbox_line(body)
        if kind == "privmsg":
            line = norm
        else:
            line = f"PRIVMSG {ch} :{body}"
    else:
        kind, norm = normalize_outbox_line(body)
        if kind == "privmsg":
            line = norm
        else:
            line = body
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # explicit utf-8 no BOM (Python open utf-8 does not write BOM)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")


def take_outbox_lines(
    path: Path, last: int, max_lines: int | None = None
) -> tuple[list[str], int]:
    """Complete newline-terminated outbox lines from byte offset `last`.

    A poll that lands mid-write must not send a truncated SEAL/FILE line
    (mode-2 flake: first OFFER seen, no DONE). Partial tail stays unconsumed.

    FR #226: strip UTF-8 BOM on the file head and per-line; normalize pre-wrapped
    PRIVMSG so drain never double-wraps.

    FR #68: optional ``max_lines`` caps how many non-empty lines are returned so
    the caller can yield between ticks (chair +o / ChanServ must not wait on a
    multi-thousand-line backlog at FLOOD_S each).
    """
    try:
        data = path.read_bytes()
    except OSError:
        return [], last
    # File-level BOM only affects offset 0
    data_for_read = data
    file_bom = 0
    if data.startswith(_BOM_UTF8):
        file_bom = len(_BOM_UTF8)
        if last == 0:
            data_for_read = data[file_bom:]
            # logical last still counts full file positions including BOM bytes
    if last > len(data):
        last = 0
    # Slice from last on full data, but skip BOM if last is within BOM
    if last < file_bom:
        buf = data[file_bom:]
        base = file_bom
    else:
        buf = data[last:]
        base = last
    lines: list[str] = []
    consumed = 0
    limit = None if max_lines is None else max(0, int(max_lines))
    while True:
        if limit is not None and len(lines) >= limit:
            break
        nl = buf.find(b"\n", consumed)
        if nl < 0:
            break
        raw = buf[consumed:nl].rstrip(b"\r")
        # drop per-line BOM bytes
        if raw.startswith(_BOM_UTF8):
            raw = raw[len(_BOM_UTF8) :]
        # decode; replace errors; strip BOM char
        text = raw.decode("utf-8", "replace")
        kind, norm = normalize_outbox_line(text)
        if kind != "empty" and norm:
            lines.append(norm)
        consumed = nl + 1
    return lines, base + consumed


def outbox_pos_path(outbox: Path) -> Path:
    return Path(str(outbox) + ".pos")


def load_outbox_pos(outbox: Path) -> int:
    """Byte offset of last successfully drained complete line. Missing → 0 (restart sends JOIN)."""
    p = outbox_pos_path(outbox)
    if not p.exists():
        return 0
    try:
        n = int(p.read_text(encoding="utf-8").strip() or "0")
    except (ValueError, OSError):
        return 0
    return n if n >= 0 else 0


def save_outbox_pos(outbox: Path, pos: int) -> None:
    outbox_pos_path(outbox).write_text(str(int(pos)) + "\n", encoding="utf-8")


def info(msg: str) -> None:
    print(msg, flush=True)



def extract_privmsg_address_prefix(text: str) -> tuple[str, str]:
    """Return (prefix, rest). Prefix is nick: / @nick, / nick - kept on every split piece."""
    t = text or ""
    m = re.match(r"^(@?[A-Za-z0-9_\[\]\\`^{|}-]+)(\s*[:,]\s*|\s+-\s+)", t)
    if not m:
        return "", t
    return m.group(0), t[m.end() :]


def privmsg_text_budget(
    *,
    nick: str,
    target: str,
    linelen: int = 512,
    user: str = "u",
    host: str = "h.irc",
) -> int:
    """Max UTF-8 bytes for PRIVMSG text so the *relayed* line fits linelen.

    Server line: ``:nick!user@host PRIVMSG target :text\\r\\n``
    """
    prefix = f":{nick}!{user}@{host} PRIVMSG {target} :"
    # linelen includes CRLF on many stacks; budget text only.
    budget = int(linelen) - 2 - len(prefix.encode("utf-8"))
    if budget < 32:
        budget = 32
    if budget > DEFAULT_PRIVMSG_TEXT_MAX:
        # still cap: unknown long host cloaks shrink room; keep a conservative ceiling
        # when linelen is the classic 512.
        if linelen <= 512:
            budget = min(budget, DEFAULT_PRIVMSG_TEXT_MAX)
    return budget


def split_utf8_by_words(text: str, max_bytes: int) -> list[str]:
    """Split text into pieces each encoding to <= max_bytes; never split a UTF-8 codepoint.

    Prefer breaks after whitespace. ``"".join(pieces) == text`` always.
    """
    if max_bytes < 1:
        max_bytes = 1
    raw = text or ""
    if len(raw.encode("utf-8")) <= max_bytes:
        return [raw] if raw != "" else [""]

    parts: list[str] = []
    start = 0
    n = len(raw)
    while start < n:
        end = start
        break_at = start
        while end < n:
            trial = raw[start : end + 1]
            if len(trial.encode("utf-8")) > max_bytes:
                break
            end += 1
            if raw[end - 1].isspace():
                break_at = end
        if end == start:
            # single codepoint longer than budget (should not happen for IRC text)
            end = start + 1
        elif end < n and break_at > start:
            end = break_at
        parts.append(raw[start:end])
        start = end
    return parts if parts else [""]


def split_privmsg_body(text: str, max_bytes: int) -> list[str]:
    """Split PRIVMSG body; keep address prefix on every piece.

    ``"".join(p[len(prefix):] for p in pieces)`` with prefix stripped once recovers
    the original body after the address prefix (pieces are prefix+chunk).
    """
    prefix, rest = extract_privmsg_address_prefix(text)
    pref_b = len(prefix.encode("utf-8"))
    room = max_bytes - pref_b
    if room < 8:
        room = max(8, max_bytes // 4)
    chunks = split_utf8_by_words(rest, room)
    if not prefix:
        return chunks
    return [prefix + c for c in chunks]


def reassemble_privmsg_bodies(pieces: list[str]) -> str:
    """Undo split_privmsg_body for tests / verification."""
    if not pieces:
        return ""
    prefix, _ = extract_privmsg_address_prefix(pieces[0])
    if not prefix:
        return "".join(pieces)
    return prefix + "".join(p[len(prefix) :] if p.startswith(prefix) else p for p in pieces)


def expand_irc_outbound_line(
    line: str,
    *,
    nick: str,
    linelen: int = 512,
    text_max: int | None = None,
) -> list[str]:
    """Expand one outbox/chat line into wire line(s). Non-PRIVMSG pass through."""
    # rstrip only CR/LF — never strip trailing body spaces (reassembly must be exact).
    s = (line or "").rstrip("\r\n").lstrip(" \t")
    if not s.upper().startswith("PRIVMSG "):
        return [s] if s else []
    # PRIVMSG target :text  OR  PRIVMSG target : (empty)
    rest = s[8:]  # after "PRIVMSG "
    if " :" not in rest:
        return [s]
    target, _, text = rest.partition(" :")
    target = target.strip()
    if not target:
        return [s]
    budget = text_max if text_max is not None else privmsg_text_budget(nick=nick, target=target, linelen=linelen)
    pieces = split_privmsg_body(text, budget)
    return [f"PRIVMSG {target} :{p}" for p in pieces]


def is_connect_throttle(text: str) -> bool:
    t = (text or "").lower()
    return "too many times" in t or "throttl" in t


def throttle_delay_s(n: int) -> float:
    """Backoff after the n-th consecutive Ergo connect-throttle ERROR (n>=1)."""
    raw = (os.environ.get("BOB_IRC_THROTTLE_BASE_S") or "120").strip()
    try:
        base = float(raw)
    except ValueError:
        base = 120.0
    base = max(1.0, base)
    return min(900.0, base * (2 ** max(0, n - 1)))



def reconnect_cap() -> int | None:
    """Max reconnect cycles after a failed session; None = unlimited."""
    raw = (os.environ.get("BOB_IRC_RECONNECT_MAX") or "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n >= 0 else None


def debug_log(path: Path | None, line: str) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


class Client:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.original_nick = args.nick
        self.live_nick = args.nick
        if getattr(args, "chair", False):
            # Jeeves: #bobiverse + every #{machine} (Simon 2026-09-22).
            self.channels = bobreport.chair_channels()
        else:
            self.channels = bobreport.channels_for_nick(args.nick, args.channel)
        if not self.channels:
            chan = args.channel if str(args.channel).startswith("#") else "#" + str(args.channel)
            if "|" in chan:
                raise ValueError("channel must not contain |")
            self.channels = [chan]
        self.chan = self.channels[0]
        self._pending_joins: set[str] = {c.lower() for c in self.channels}
        self._last_call_channel: str | None = None
        if args.home:
            os.environ["BOB_HOME"] = str(Path(args.home).expanduser())
        self.home = seal.home()
        # #53: first start under the jeeves/bobiverse home names -> copy data from the old
        # ~\\.agentic-irc-* home (kept as backup). Idempotent; never blocks the connect.
        try:
            if getattr(args, "chair", False):
                bob_home.ensure_homes(chair=self.home, digest=bob_home.digest_home(), log=info)
                for _n in bob_home.migrate_secrets_to_config(
                    bob_home.config_dir(), homes=[self.home, bob_home.digest_home()]
                ):
                    info(f"INFO config secret {_n} migrated into {bob_home.config_dir()}")
            else:
                bob_home.ensure_homes(digest=self.home, log=info)
        except Exception as exc:  # pragma: no cover
            info(f"WARN home-migration skipped {type(exc).__name__}")
        self.home.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.home)
        if getattr(args, "chair", False):
            bobreport.persist_chair_nick(self.home, args.nick)
        self.outbox = Path(args.outbox) if args.outbox else self.home / "outbox.txt"
        self.inbox = self.home / "inbox"
        self.inbox.mkdir(parents=True, exist_ok=True)
        protect.protect_path(self.inbox)
        self.debug = self.home / "irc.log" if os.environ.get("BOB_IRC_DEBUG") else None
        self.ident = seal.load_ident() if seal.ident_path().exists() else None
        self.peers = seal.load_peers()
        self.fragments = seal.FragmentStore()
        self._moot: dict = {}
        self.file_bags = filexfer.FileBag()
        self.lock = threading.Lock()
        self.sock: ssl.SSLSocket | None = None
        self._outbox_gen = 0
        self._linelen = 512
        self._privmsg_text_max: int | None = None  # None → derive from nick/target/linelen
        self.ready = threading.Event()
        self.joined = threading.Event()
        self.dead = threading.Event()
        self.stop = threading.Event()
        self.sasl_ack = threading.Event()
        self.sasl_plus = threading.Event()
        self.sasl_903 = threading.Event()
        self.sasl_fail = threading.Event()
        self._nickname_reserved = False
        # FR #230: nick -> services account (CAP account-notify / extended-join / account-tag)
        try:
            from account_map import AccountMap

            self.accounts = AccountMap()
            self.accounts.load(self.home / "accounts.json")
        except Exception:
            self.accounts = None
        self._bobiverse_last_query: dict[str, float] = {}
        self._bobiverse_last_tray: dict[str, float] = {}
        self._bobiverse_pull_last = 0.0
        # #42: ChanServ roster mirror (chair only). Query state; registry file is the cache.
        self._cs_collector: registered_machines.ChanServListCollector | None = None
        self._cs_sent_at = 0.0
        self._cs_force = False
        self._cs_fail_at = 0.0
        self._cs_list_status = "unknown"  # unknown | ok | denied
        # Chair OPER + channel-op upkeep (see chair_oper.py).
        self._oper_state = "off"  # off | nocred | pending | ok | failed
        self._oper_name = ""
        self._oper_done = threading.Event()
        self._chan_op: dict[str, bool] = {}
        self._op_try_at: dict[str, float] = {}
        self._chair_status_at = 0.0
        self._chair_status_last = ""
        self._digest_asm = bobreport.DigestWhisperAssembler()
        self._report_gone_told: set[str] = set()
        self._pm_open: dict[str, float] = {}
        self._action_last: dict[tuple[str, str], float] = {}
        self._mention_last: dict[str, float] = {}
        self._grok_talk_dedup: dict[tuple[str, str], float] = {}
        self._no_reconnect = False
        self._last_server_rx = 0.0
        self._pong_due_at = 0.0
        self._ghost_prune_last = 0.0

    def send(self, line: str) -> None:
        assert self.sock is not None
        with self.lock:
            self.sock.sendall((line + "\r\n").encode("utf-8"))

    def _channel_only_worker(self) -> bool:
        """FR #224: {machine}-{pid} / w-* seats never PRIVMSG a nick."""
        if getattr(self.args, "chair", False):
            return False
        nick = self.original_nick or self.live_nick or ""
        return channel_only.is_channel_only_worker_nick(nick)

    def send_privmsg_lines(self, line: str) -> list[str]:
        """Send PRIVMSG (splitting if needed). Returns wire lines actually sent.

        FR #224: channel-only workers rewrite PRIVMSG <nick> to PRIVMSG #{machine}.
        """
        nick = self.live_nick or self.original_nick or "agent"
        if self._channel_only_worker():
            line = channel_only.rewrite_worker_outbound_line(self.original_nick or nick, line)
        wire_lines = expand_irc_outbound_line(
            line,
            nick=nick,
            linelen=getattr(self, "_linelen", 512) or 512,
            text_max=getattr(self, "_privmsg_text_max", None),
        )
        out: list[str] = []
        for w in wire_lines:
            # Final guard: never emit nick target from worker seat
            if self._channel_only_worker():
                w = channel_only.rewrite_worker_outbound_line(self.original_nick or nick, w)
                bad = channel_only.assert_no_worker_nick_privmsg(self.original_nick or nick, [w])
                if bad:
                    info(f"INFO channel-only blocked nick-PRIVMSG {w[:80]!r}")
                    continue
            self.send(w)
            out.append(w)
            if len(wire_lines) > 1:
                time.sleep(FLOOD_S)
        return out

    def say(self, msg: str) -> None:
        dest = self._reply_channel()
        if self._channel_only_worker():
            shop = self._shop_channel() or channel_only.worker_own_shop(self.original_nick or "")
            if shop:
                dest = shop
        self.send_privmsg_lines("PRIVMSG " + dest + " :" + msg)
        time.sleep(FLOOD_S)

    def _reply_channel(self) -> str:
        """Prefer last inbound joined channel (call channel); else primary JOIN."""
        last = (self._last_call_channel or "").strip()
        if last and self._joined_channel(last):
            return bobreport.normalize_channel(last) or self.chan
        return self.chan

    def _note_call_channel(self, target: str) -> None:
        if not self._joined_channel(target):
            return
        ch = bobreport.normalize_channel(target)
        if ch:
            self._last_call_channel = ch

    def _joined_channel(self, target: str) -> bool:
        t = bobreport.normalize_channel(target).lower()
        return t in {c.lower() for c in self.channels}

    def _shop_channel(self) -> str | None:
        worker = bobreport.parse_worker_nick(self.original_nick)
        if worker:
            return bobreport.shop_channel(worker[0])
        mid = bobreport.machine_from_nick(self.original_nick)
        if mid:
            return bobreport.shop_channel(mid)
        return None

    def whisper(self, nick: str, msg: str) -> None:
        """PM a nick. FR #224: channel-only workers redirect to own shop instead."""
        target = (nick or "").strip()
        if not target or "|" in target:
            return
        if self._channel_only_worker():
            shop = self._shop_channel() or channel_only.worker_own_shop(self.original_nick or "")
            if not shop:
                info("INFO channel-only drop whisper (no shop)")
                return
            info(f"INFO channel-only whisper->shop {shop}")
            self.send_privmsg_lines("PRIVMSG " + shop + " :" + msg)
            time.sleep(FLOOD_S)
            return
        self.send_privmsg_lines("PRIVMSG " + target + " :" + msg)
        time.sleep(FLOOD_S)

    def _mine_nicks(self) -> set[str]:
        return {self.original_nick.lower(), self.live_nick.lower()}

    def _fleet_moot_state(self) -> dict:
        disk = moot.load_state(self.home, bobtalk.FLEET_MOOT_ID)
        if disk.get("id") == bobtalk.FLEET_MOOT_ID:
            return disk
        if self._moot.get("id") == bobtalk.FLEET_MOOT_ID:
            return self._moot
        return disk or self._moot or {}

    def _online_bob_nicks(self) -> set[str]:
        doc = bobreport.load_digest(self.home)
        machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
        out: set[str] = set()
        for ent in machines.values():
            if isinstance(ent, dict) and ent.get("online"):
                nick = str(ent.get("nick") or "").strip()
                if nick.lower().startswith("bob-"):
                    out.add(nick.lower())
        return out

    def _is_briefer(self) -> bool:
        return bobtalk.is_briefer(self._fleet_moot_state(), self.live_nick, self._online_bob_nicks())

    def _is_digest_operator(self) -> bool:
        return bobtalk.is_digest_operator(
            self._fleet_moot_state(), self.live_nick, self._online_bob_nicks(), self.home
        )

    def _deliver_whispers(self, nick: str, lines: list[str]) -> None:
        for line in lines:
            if line:
                self.whisper(nick, line)

    def _fleet_joiner(self, nick: str) -> bool:
        return (nick or "").strip().lower().startswith("bob-")

    def _maybe_brief_joiner(self, nick: str) -> None:
        joiner = (nick or "").strip()
        if not joiner or joiner.lower() in self._mine_nicks():
            return
        if not self._fleet_joiner(joiner):
            return
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        if not self._is_briefer():
            return
        lines = bobtalk.network_talk_lines(self.home)
        self._deliver_whispers(joiner, lines)
        info(f"INFO bobiverse brief to={joiner} lines={len(lines)}")

    def _handle_report(self, sender: str, _on_channel: bool, body: str) -> None:
        who = (sender or "").strip()
        if not who or not self._is_digest_operator():
            return
        if bobreport.looks_like_secret(body):
            return
        key = who.lower()
        if key in self._report_gone_told:
            return
        self._report_gone_told.add(key)
        self.whisper(who, bobreport.REPORT_GONE)

    def _fleet_action(self, event_class: str, key: str, text: str) -> None:
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        if not self._is_digest_operator() or not text:
            return
        if bobreport.looks_like_secret(text):
            return
        now = time.time()
        stamp = (event_class, key)
        last = self._action_last.get(stamp, 0.0)
        if now - last < bobreport.ACTION_COOLDOWN_S:
            return
        self._action_last[stamp] = now
        self.send("PRIVMSG " + bobreport.FLEET_CHANNEL + " :\x01ACTION " + text + "\x01")
        time.sleep(FLOOD_S)

    def _emit_presence(self, outcome: bobreport.PresenceOutcome, event_class: str, key: str) -> None:
        if not bobtalk.fleet_status_to_channel_enabled(self.home):
            return
        for action in outcome.actions:
            self._fleet_action(event_class, key, action)

    def handle_join(self, nick: str, channel: str) -> None:
        expanded = bobreport.expand_join_channels(channel)
        if len(expanded) > 1:
            for ch in expanded:
                self.handle_join(nick, ch)
            return
        who = (nick or "").strip()
        ch = bobreport.normalize_channel(expanded[0] if expanded else channel)
        if who.lower() in self._mine_nicks():
            self._pending_joins.discard(ch.lower())
            if not self._pending_joins:
                self.joined.set()
            if not bobreport.worker_channel_allowed(self.original_nick, ch):
                # CAST IRON: workers live in #{machine} only - leave anything else.
                try:
                    self.send("PART " + ch + " :workers join #{machine} only")
                except (OSError, AttributeError):
                    pass
                info(f"INFO worker auto-PART {ch} (workers join own #machine only)")
                return
        if who and who.lower() not in self._mine_nicks() and ch.lower() == bobreport.FLEET_CHANNEL:
            self._maybe_brief_joiner(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_join(self.home, who, ch, briefer)
        self._emit_presence(out, "join", f"{who}:{ch}")

    def handle_part(self, nick: str, channel: str) -> None:
        who = (nick or "").strip()
        ch = bobreport.normalize_channel(channel)
        self._maybe_local_shop_closed(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_part(self.home, who, ch, briefer)
        klass = "shop-down" if out.shop_closed else "drop"
        self._emit_presence(out, klass, f"{who}:{ch}")

    def handle_quit(self, nick: str) -> None:
        who = (nick or "").strip()
        self._maybe_local_shop_closed(who)
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        # FR #211: worker QUIT mid-task → idle webhook + job back to unaccepted
        try:
            q = shop_listen.handle_shop_worker_quit(self.home, nick=who, briefer=briefer)
            if q.get("handled"):
                info(
                    f"INFO shop-listen quit nick={who} returned={q.get('returned')} "
                    f"webhook={q.get('webhook')}"
                )
        except Exception as exc:
            info(f"INFO shop-listen quit error {type(exc).__name__}")
        out = bobreport.apply_quit(self.home, who, briefer)
        klass = "shop-down" if out.shop_closed else "drop"
        self._emit_presence(out, klass, who)

    def _maybe_local_shop_closed(self, departed: str) -> None:
        mid = bobreport.machine_from_nick(departed)
        mine = bobreport.parse_worker_nick(self.original_nick)
        if not mid or not mine or mine[0] != mid:
            return
        shop = bobreport.shop_channel(mid)
        for nick in list(self._pm_open):
            try:
                self.whisper(nick, "shop closed")
            except Exception:
                pass
        self.request_shutdown(":shop closed")

    def _digest_home(self) -> Path:
        return bobreport.fleet_digest_home(self.home)

    def _cc_working_on(self, text: str) -> None:
        worker = bobreport.parse_worker_nick(self.original_nick)
        if not worker:
            return
        mid, pid = worker
        raw = (text or "").strip()
        if not raw:
            return
        out = bobreport.merge_worker_working_on(self._digest_home(), mid, pid, raw)
        if not out.ok or not out.actions:
            return
        nick = self.live_nick or self.original_nick
        # Issue #167: webhook only — no shop PRIVMSG for working_on.
        try:
            import post_working_on as _pwo

            payload = _pwo.base_payload(mid, int(pid), nick, "cursor", "running")
            payload["working_on"] = raw
            code = _pwo.post(payload)
            info(f"INFO working_on webhook POST {code} machine={mid} pid={pid}")
        except Exception as exc:  # noqa: BLE001 — never break IRC announce on webhook fail
            info(f"INFO working_on webhook skip: {exc}")

    def apply_digest_callback(self, payload: dict) -> None:
        if not self._is_digest_operator():
            return
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
        out = bobreport.apply_callback(self.home, payload, briefer)
        if not out.ok or not out.actions:
            return
        actions = out.actions
        pid_raw = payload.get("pid")
        mid = bobreport.normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
        key = f"{mid}:{pid_raw}" if mid and pid_raw is not None else str(mid or "merge")
        out = bobreport.PresenceOutcome(ok=True, actions=actions, machine_id=mid)
        self._emit_presence(out, "working_on", key)

    def cc_send(self, kind: str, text: str) -> None:
        k = (kind or "").strip().lower().replace("-", "_")
        if k == "working_on":
            self._cc_working_on(text)
            return
        pieces = bobreport.split_irc_text(text)
        dests = bobreport.route_cc(kind, bool(self._pm_open))
        shop = self._shop_channel()
        for piece in pieces:
            if bobreport.CC_SHOP in dests and shop and shop.lower() != bobreport.FLEET_CHANNEL:
                self.send("PRIVMSG " + shop + " :" + piece)
                time.sleep(FLOOD_S)
            if bobreport.CC_QUERY in dests:
                for nick in list(self._pm_open):
                    self.whisper(nick, piece)

    def _mark_pm_open(self, nick: str) -> None:
        n = (nick or "").strip()
        if not n or n.lower() in self._mine_nicks():
            return
        if n.lower().startswith("bob-") or bobreport.parse_worker_nick(n):
            return
        self._pm_open[n.lower()] = time.time()

    def _answer_bobiverse(self, asker: str, body: str) -> bool:
        """!bobiverse removed (#174). Whisper one-line pointer to public digest URL."""
        who = (asker or "").strip()
        if not who or who.lower() in self._mine_nicks():
            return True
        if not self._is_digest_operator():
            return True
        parsed = bobreport.parse_bobiverse_query(body)
        if not parsed:
            return True
        now = time.time()
        key = who.lower()
        last = self._bobiverse_last_query.get(key, 0.0)
        if now - last < bobtalk.BOBIVERSE_COOLDOWN_S:
            return True
        self._bobiverse_last_query[key] = now
        self._deliver_whispers(who, [bobreport.BOBIVERSE_GONE])
        info(f"INFO bobiverse refused to={who} url={bobreport.digest_url()}")
        return True

    def _register_operators(self) -> set[str]:
        """Simon + configured operators may !register (bobiverse)."""
        ops = {"simon"}
        p = Path(self.home) / "operators.txt"
        if p.is_file():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                s = line.strip().lstrip("\ufeff")
                if s and not s.startswith("#"):
                    ops.add(s.lower())
        return ops

    # ---- #42: ChanServ-registered machine channels are the roster (mirror, add AND remove)
    # ---- chair: OPER on connect + channel +o upkeep ------------------------------------
    def _chair_reset_session(self) -> None:
        self._oper_state = "off"
        self._oper_done.clear()
        self._chan_op = {}
        self._op_try_at = {}
        self._cs_list_status = "unknown"
        self._cs_collector = None
        eng = getattr(self, "_privs_engine", None)
        if eng is not None:
            eng.reset()

    def _chair_oper_on_connect(self) -> None:
        """Send OPER with the install-config credentials and wait briefly for 381 / +o."""
        if not getattr(self.args, "chair", False):
            return
        path = chair_oper.cred_path(bob_home.config_dir())
        cred = chair_oper.load_credentials(path)
        if cred is None:
            self._oper_state = "nocred"
            info(
                f"WARN OPER SKIPPED: no readable oper credentials at {path} - Jeeves is NOT an IRC "
                "operator (no ChanServ LIST, no SAMODE). Re-run Install-Jeeves.ps1 with -OperFile "
                "<ergo-oper file> or -OperName/-OperPassword."
            )
            return
        self._oper_name = cred[0]
        self._oper_state = "pending"
        self._oper_done.clear()
        info(f"INFO OPER sending as '{cred[0]}' (credentials from {path}; value not logged)")
        self.send(f"OPER {cred[0]} {cred[1]}")
        if not self._oper_done.wait(8):
            self._oper_state = "failed"
            info("WARN OPER: no reply (381/464/491) within 8s - treating as NOT oper")
        self._chair_log_status(force=True)

    def _on_oper_numeric(self, cmd: str, parts: list[str], trailing: str) -> None:
        if cmd == "381":
            self._oper_state = "ok"
            self._oper_done.set()
            info(f"INFO OPER OK: 381 RPL_YOUREOPER as '{self._oper_name}' - Jeeves is an IRC operator")
        elif cmd in ("464", "491", "481") and self._oper_state == "pending":
            self._oper_state = "failed"
            self._oper_done.set()
            info(
                f"ERROR OPER FAILED: {cmd} {(trailing or '').strip()[:80]} for '{self._oper_name}' "
                "- wrong oper name/password or ircd.yaml has no such oper; Jeeves is NOT an operator"
            )
        elif cmd in ("221", "MODE"):
            modes = parts[2] if cmd == "221" and len(parts) > 2 else (parts[2] if len(parts) > 2 else "")
            target = parts[1] if len(parts) > 1 else ""
            if (cmd == "221" or target.lower() == self.live_nick.lower()) and chair_oper.umode_has_o(modes):
                if self._oper_state != "ok":
                    info("INFO OPER OK: user mode +o set on Jeeves")
                self._oper_state = "ok"
                self._oper_done.set()

    def _on_chair_channel_line(self, cmd: str, parts: list[str], trailing: str) -> None:
        if not getattr(self.args, "chair", False):
            return
        if cmd == "353":
            r = chair_oper.names_has_op(parts, trailing, self.live_nick)
            if r is not None and (r[1] or r[0].lower() not in self._chan_op):
                self._chan_op[r[0].lower()] = r[1]
        elif cmd == "MODE":
            for chan, mode, added in chair_oper.mode_changes_for(parts, self.live_nick):
                if mode in "oaq":
                    self._chan_op[chan.lower()] = added
                    if added:
                        info(f"INFO chair +{mode} in {chan}")
                    else:
                        # mode drift: Jeeves lost ops - retry immediately (not after the 45 s back-off)
                        self._op_try_at.pop(chan.lower(), None)
                        info(f"WARN chair -{mode} in {chan}: Jeeves lost ops, re-applying")
        elif cmd in ("PART", "KICK"):
            pass

    # ---- v0.1.18: channel privilege rules + worker list (chair only; see chan_privs / chan_workers)
    def _privs(self):
        eng = getattr(self, "_privs_engine", None)
        if eng is None:
            eng = chan_privs.ChanPrivEngine(
                send=self.send,
                log=info,
                now=time.time,
                me=lambda: self.live_nick,
                channels=lambda: list(self.channels),
                is_registered=lambda mid: registered_machines.is_registered(self._digest_home(), mid),
                normalize=bobreport.normalize_machine_id,
                chan_op=lambda ch: bool(self._chan_op.get(ch.lower())),
                is_oper=lambda: getattr(self, "_oper_state", "") == "ok",
                on_names=self._on_channel_names,
                skip_whois=self._privs_skip_whois,
            )
            self._privs_engine = eng
        return eng

    def _privs_skip_whois(self, nick: str) -> bool:
        """No account lookup for ears, seats, Jeeves or IRC services - they never earn owner ops."""
        low = (nick or "").lower()
        if low in self._mine_nicks() or low.endswith("serv") or low == "global":
            return True
        return bool(
            registered_machines.machine_from_bob_nick(nick) or bobreport.parse_seat_nick(nick)
            or not bobreport.is_worker_nick(nick) and low != "simon" and low.startswith(("bob-", "console-"))
        )

    def _workers(self):
        wk = getattr(self, "_worker_tracker", None)
        if wk is None:
            wk = chan_workers.WorkerTracker(self._digest_home(), log=info)
            self._worker_tracker = wk
        return wk

    def _on_channel_names(self, chan: str, present: set) -> None:
        try:
            self._workers().reconcile(chan, present)
        except Exception as exc:  # never kill the reader over the worker list
            info(f"WARN workers reconcile error {type(exc).__name__}")

    def _chair_wire(self, cmd: str, parts: list, trailing: str, prefix: str, tags: dict) -> None:
        """Chair: feed membership/mode/account events to the privilege engine and the worker list."""
        if not getattr(self.args, "chair", False):
            return
        try:
            self._privs().on_line(cmd, parts, trailing, prefix, tags)
            who = chan_privs.clean_nick(prefix.split("!", 1)[0]) if prefix else ""
            if not who or (who.lower() in self._mine_nicks() and cmd != "KICK"):
                return        # own PART/QUIT/NICK; but a KICK *by* Jeeves still removes the kicked worker
            if cmd in ("PART", "KICK"):
                chan = parts[1].lstrip(":") if len(parts) > 1 else trailing
                gone = (parts[2].lstrip(":") if cmd == "KICK" and len(parts) > 2 else who)
                self._workers().on_leave(gone, chan)
            elif cmd == "QUIT":
                self._workers().on_quit(who)
            elif cmd == "NICK":
                new = (parts[1] if len(parts) > 1 else trailing).lstrip(":")
                self._workers().on_nick(who, new)
        except Exception as exc:  # noqa: BLE001
            info(f"WARN chair-wire {cmd} error {type(exc).__name__}: {exc}"[:200])

    def _chan_privs_tick(self) -> None:
        if not getattr(self.args, "chair", False) or not self.joined.is_set():
            return
        try:
            self._privs().tick()
        except OSError:
            raise
        except Exception as exc:  # noqa: BLE001 - never kill the outbox loop over the reconcile
            info(f"WARN chan-privs tick error {type(exc).__name__}: {exc}"[:200])

    def _ensure_chan_ops(self) -> None:
        """Chair must hold +o in #bobiverse and every machine channel (SAMODE as oper; else ChanServ OP)."""
        if not getattr(self.args, "chair", False) or not self.joined.is_set():
            return
        now = time.time()
        for ch in list(self.channels):
            key = ch.lower()
            if self._chan_op.get(key):
                continue
            if now - self._op_try_at.get(key, 0.0) < 45.0:
                continue
            self._op_try_at[key] = now
            try:
                if self._oper_state == "ok":
                    self.send(f"SAMODE {ch} +o {self.live_nick}")
                    info(f"INFO chair not +o in {ch}: SAMODE {ch} +o {self.live_nick} (oper samode)")
                else:
                    self.send(f"PRIVMSG ChanServ :OP {ch}")
                    info(
                        f"WARN chair not +o in {ch} and not oper (oper={self._oper_state}); "
                        "asked ChanServ OP (works only with founder/AMODE)"
                    )
            except OSError:
                return
        self._chair_log_status()

    def _chair_status_line(self) -> str:
        ops = sorted(c for c in (x.lower() for x in self.channels) if self._chan_op.get(c))
        missing = sorted(c.lower() for c in self.channels if not self._chan_op.get(c.lower()))
        return (
            f"oper={self._oper_state} chanserv-list={self._cs_list_status} "
            f"op-in={','.join(ops) or '-'} NOT-op-in={','.join(missing) or '-'}"
        )

    def _chair_log_status(self, force: bool = False) -> None:
        line = self._chair_status_line()
        now = time.time()
        if force or line != self._chair_status_last or now - self._chair_status_at > 300.0:
            level = "INFO" if (self._oper_state == "ok" and "NOT-op-in=-" in line) else "WARN"
            info(f"{level} chair-status {line}")
            self._chair_status_last = line
            self._chair_status_at = now

    def _cs_ttl_s(self) -> float:
        try:
            return max(15.0, float(os.environ.get("BOB_CHANSERV_SYNC_TTL_S") or 120.0))
        except ValueError:
            return 120.0

    def _maybe_chanserv_sync(self) -> None:
        """Chair: periodically send ``ChanServ LIST`` (oper ``chanreg``); the NOTICE replies
        are mirrored into registered-machines.json by :meth:`_on_chanserv_notice`."""
        if not getattr(self.args, "chair", False) or not self.joined.is_set():
            return
        now = time.time()
        if self._cs_collector is not None:
            if now - self._cs_sent_at > 30.0:  # no End marker: outage / lost reply
                info("INFO chanserv-sync timeout; keeping last good roster")
                self._cs_collector = None
                self._cs_fail_at = now
            return
        digest = self._digest_home()
        due = self._cs_force or registered_machines.refresh_due(digest, self._cs_ttl_s(), now)
        if not due:
            return
        if not self._cs_force and now - self._cs_fail_at < 30.0:
            return  # back off after a failed attempt
        self._cs_force = False
        self._cs_collector = registered_machines.ChanServListCollector()
        self._cs_sent_at = now
        try:
            self.send("PRIVMSG ChanServ :LIST")
        except OSError:
            self._cs_collector = None
            self._cs_fail_at = now

    def _on_chanserv_notice(self, text: str) -> None:
        col = self._cs_collector
        if col is None:
            return
        ev = col.feed(text)
        if ev == "error":
            self._cs_list_status = "denied"
            info(
                f"ERROR chanserv LIST DENIED ({col.error}); oper={self._oper_state}. "
                "Needs Ergo oper capability 'chanreg': "
                + chair_oper.CHANREG_HINT % (self._oper_name or "<jeeves oper>")
                + " Keeping last roster."
            )
            self._cs_collector = None
            self._cs_fail_at = time.time()
        elif ev == "end":
            self._cs_collector = None
            if self._cs_list_status != "ok":
                info("INFO chanserv LIST OK (oper has chanreg)")
            self._cs_list_status = "ok"
            self._apply_chanserv_channels(col.channels)

    def _apply_chanserv_channels(self, channels: list[str]) -> None:
        digest = self._digest_home()
        res = registered_machines.sync_from_chanserv(digest, channels)
        if res is None:
            info("INFO chanserv-sync empty/unusable result; keeping last roster")
            self._cs_fail_at = time.time()
            return
        added, removed = res
        info(f"INFO chanserv-sync ok machines={len(registered_machines.load_registered(digest))} "
             f"+{sorted(added)} -{sorted(removed)}")
        have = {c.lower() for c in self.channels}
        for mid in sorted(added):
            shop = f"#{mid}"
            if shop.lower() not in have:
                self.channels.append(shop)
                try:
                    self.send(f"JOIN {shop}")
                except OSError:
                    pass
        for mid in sorted(removed):
            shop = f"#{mid}"
            self.channels = [c for c in self.channels if c.lower() != shop.lower()]
            try:
                self.send(f"PART {shop} :no longer registered")
            except OSError:
                pass

    def _handle_register_command(self, asker: str, body: str) -> bool:
        """Chair: !register <machine> → ChanServ REGISTER #{machine} + persist."""
        if not getattr(self.args, "chair", False):
            return False
        mid = registered_machines.parse_register_command(body)
        if not mid:
            return False
        who = (asker or "").strip()
        if not who or who.lower() in self._mine_nicks():
            return True
        if who.lower() not in self._register_operators():
            self.whisper(who, f"ERR !register denied (operators only) machine={mid}")
            info(f"INFO register denied nick={who} machine={mid}")
            return True
        shop = f"#{mid}"
        if shop.lower() not in {c.lower() for c in self.channels}:
            self.channels.append(shop)
            self.send(f"JOIN {shop}")
            time.sleep(FLOOD_S)
        # Jeeves owns registration (Bob does not self-REGISTER).
        self.send(f"PRIVMSG ChanServ :REGISTER {shop}")
        time.sleep(FLOOD_S)
        registered_machines.add_registered(self._digest_home(), mid)
        self._cs_force = True  # #42: re-sync the mirror from ChanServ right away
        self.whisper(who, f"ACK registered {shop}")
        info(f"INFO register machine={mid} by={who}")
        return True

    def _maybe_grant_bob_modes(self, nick: str) -> None:
        """Merged into chan_privs (v0.1.18): bob-<machine> +o in #<machine>, +h in #bobiverse, re-applied
        on JOIN / mode drift / reconcile by the privilege engine. Kept as an explicit re-apply hook."""
        if not getattr(self.args, "chair", False):
            return
        mid = registered_machines.machine_from_bob_nick(nick)
        if not mid:
            return
        eng = self._privs()
        for ch in (f"#{mid}", bobreport.FLEET_CHANNEL):
            eng.apply(ch, "bob-join")

    def _handle_recycle_command(self, asker: str, body: str) -> None:
        if not getattr(self.args, "chair", False):
            return
        parsed = bob_recycle.parse_recycle_query(body)
        if not parsed:
            return
        kind, machine_id = parsed
        who = (asker or "").strip()
        if not who or who.lower() in self._mine_nicks():
            return
        if kind == "refuse":
            if who:
                self.whisper(who, bob_recycle.refuse_message(machine_id))
            return
        mid = machine_id or ""
        # !recycle jeeves → restart chair (MSI self-update on start).
        if mid.lower() in {"jeeves", "ircjeeves"}:
            try:
                self.say("Jeeves departing (recycle)")
            except Exception:
                pass
            if who:
                self.whisper(who, "ACK recycle jeeves")
            info("INFO recycle jeeves")
            try:
                import agent_control

                agent_control.request_agent_quit(self.home, "recycle-jeeves")
            except Exception:
                pass
            return
        if bob_recycle.chair_targets_local(mid):
            bob_recycle.execute_local_recycle(
                mid, self.home, ionos_chair=True, hooks=getattr(self, "_recycle_hooks", None)
            )
            if who:
                self.whisper(who, bob_recycle.ack_message(mid, local=True))
            info(f"INFO recycle local machine={mid}")
            try:
                import agent_control

                agent_control.request_agent_quit(self.home, "recycle-chair")
            except Exception:
                pass
            return
        wire = bob_recycle.format_recycle_wire(mid)
        dest = bobreport.FLEET_CHANNEL
        self.send("PRIVMSG " + dest + " :" + wire)
        time.sleep(FLOOD_S)
        if who:
            self.whisper(who, bob_recycle.ack_message(mid, local=False))
        info(f"INFO recycle wire machine={mid}")

    def _announce_departure(self, reason: str) -> None:
        """Announce leaving #bobiverse and #{machine} before recycle/restart."""
        mid = self._local_machine_id() or ""
        nick = self.live_nick or self.original_nick or "Bob"
        msg = f"{nick} departing ({reason})"
        try:
            self.send("PRIVMSG " + bobreport.FLEET_CHANNEL + " :" + msg)
            time.sleep(FLOOD_S)
        except Exception:
            pass
        if mid:
            try:
                self.send("PRIVMSG #" + mid + " :" + msg)
                time.sleep(FLOOD_S)
            except Exception:
                pass
        info(f"INFO depart announce reason={reason} machine={mid}")

    def _handle_bob_local_recycle_command(self, asker: str, body: str) -> None:
        """Bob ear: !recycle / !recycle {this-machine} → announce + local recycle."""
        if getattr(self.args, "chair", False):
            return
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return
        parsed = bob_recycle.parse_recycle_query(body)
        if not parsed:
            return
        kind, machine_id = parsed
        local = self._local_machine_id()
        if not local:
            return
        who = (asker or "").strip()
        # Bare !recycle (refuse/None) or explicit this machine
        if kind == "refuse" and machine_id is None:
            mid = local
        elif kind == "run" and (machine_id or "").lower() == local:
            mid = local
        else:
            return
        ops = {"simon", "jeeves"}
        if who and who.lower() not in ops and who.lower() not in self._mine_nicks():
            # Allow Jeeves + Simon; other operators via operators.txt in bob home
            op_file = Path(self.home) / "operators.txt"
            allowed = set(ops)
            if op_file.is_file():
                for line in op_file.read_text(encoding="utf-8-sig").splitlines():
                    s = line.strip().lstrip("\ufeff")
                    if s and not s.startswith("#"):
                        allowed.add(s.lower())
            if who.lower() not in allowed:
                return
        self._announce_departure("recycle")
        if who:
            try:
                self.whisper(who, f"ACK recycle {mid}")
            except Exception:
                pass
        bob_recycle.execute_local_recycle(
            mid, self.home, ionos_chair=False, hooks=getattr(self, "_recycle_hooks", None)
        )
        info(f"INFO bob local recycle machine={mid} from={who}")

    def _maybe_execute_recycle_wire(self, src: str, body: str) -> bool:
        if getattr(self.args, "chair", False):
            return False
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return False
        local = self._local_machine_id()
        if not local:
            return False
        # FR #197 route or legacy RECYCLE v1
        jeeves = bob_recycle.parse_jeeves_recycle_route(body)
        if jeeves:
            mid, scope = jeeves
            if scope == "fleet" or mid == "fleet":
                mid = local
            elif mid != local:
                return False
        else:
            mid = bob_recycle.parse_recycle_wire(body)
            if not mid or mid != local:
                return False
        chair = (bobreport.digest_chair_nick(self.home) or "").strip().lower()
        if not chair or src.strip().lower() != chair:
            return False
        self._announce_departure("recycle")
        info(f"INFO recycle announcing restart machine={mid} from={src}")
        bob_recycle.execute_local_recycle(
            mid, self.home, ionos_chair=(mid == bob_recycle.chair_home_machine()), hooks=getattr(self, "_recycle_hooks", None)
        )
        info(f"INFO recycle wire accepted machine={mid} from={src}")
        return True

    def _local_machine_id(self) -> str | None:
        return bobreport.machine_from_nick(self.original_nick)

    def _maybe_register_shop_chanserv(self) -> None:
        """FR #313: bob-* REGISTER #{machine} with ChanServ after JOIN.

        Best-effort NickServ IDENTIFY/REGISTER first so Ergo channel registration
        (which requires a services account) can succeed when enabled.
        Failures are ignored in the reader (services may still be off).
        """
        nick = self.original_nick or self.live_nick or ""
        lines = shop_chanserv.register_lines_for_bob(nick, self.channels)
        if not lines:
            return
        pw = shop_chanserv.ensure_bob_nickserv_password(self.home, mint=True)
        mid = bobreport.machine_from_nick(nick) or "fleet"
        if pw:
            for ns in shop_chanserv.nickserv_register_identify_lines(
                nick, pw, f"{nick}@{mid}.local"
            ):
                try:
                    self.send(ns)
                except OSError:
                    return
            time.sleep(0.3)
        for line in lines:
            try:
                self.send(line)
                info(f"INFO chanserv REGISTER {line.split()[-1]}")
            except OSError:
                info("INFO chanserv REGISTER send failed")
                return

    def _should_bobiverse_pull(self) -> bool:
        return bobreport.should_periodic_bobiverse_pull(
            self.original_nick, chair=bool(getattr(self.args, "chair", False))
        )

    def _maybe_prune_talk_seat_ghosts(self) -> None:
        if not self.original_nick.lower().startswith("bob-"):
            return
        if not self.joined.is_set():
            return
        now = time.time()
        if now - self._ghost_prune_last < 45.0:
            return
        pw = (self.args.password or os.environ.get("BOB_IRC_PASSWORD") or "").strip()
        if not pw:
            return
        mid = self.original_nick[4:]
        pruned = talk_seat_ghost.maybe_prune_local_ghosts(
            self.original_nick,
            self.args.host,
            int(self.args.port),
            pw,
        )
        self._ghost_prune_last = now
        if pruned:
            info(f"INFO ghost-prune nicks={','.join(pruned)}")

    def _maybe_depart_request(self) -> None:
        """Tray/shortcut sets depart-request.txt → announce then quit for service restart."""
        if getattr(self.args, "chair", False):
            return
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return
        flag = Path(self.home) / "depart-request.txt"
        if not flag.is_file():
            return
        try:
            reason = flag.read_text(encoding="utf-8").strip() or "tray-restart"
            flag.unlink(missing_ok=True)
        except OSError:
            return
        self._announce_departure(reason)
        try:
            import agent_control

            agent_control.request_agent_quit(self.home, f"depart-{reason}")
        except Exception:
            pass
        info(f"INFO depart-request handled reason={reason}")

    def _maybe_bobiverse_pull(self) -> None:
        """Refresh local digest via public HTTP GET (#174). No IRC !bobiverse."""
        if not self._should_bobiverse_pull():
            return
        now = time.time()
        if now - self._bobiverse_pull_last < bobtalk.BOBIVERSE_AGENT_COOLDOWN_S:
            return
        self._bobiverse_pull_last = now
        doc = bobreport.fetch_digest_http()
        if not isinstance(doc, dict):
            info("INFO digest http pull failed")
            return
        self._on_digest_http(doc)
        info(f"INFO digest http pull ok url={bobreport.digest_url()}")

    def _on_digest_http(self, doc: dict) -> None:
        if not isinstance(doc.get("machines"), dict):
            return
        if not self._should_bobiverse_pull():
            return
        mid = self._local_machine_id()
        machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
        chair_ent = machines.get(mid) if mid else None
        payload = None
        if mid and isinstance(chair_ent, dict):
            payload = bobreport.merge_payload_local_peer_ahead_of_chair(self.home, mid, chair_ent)
        bobreport.ingest_fleet_digest_pull(self.home, doc)
        if not payload:
            return
        try:
            import post_working_on as _pwo

            _pwo.post(payload)
        except Exception:
            pass

    def _on_digest_whisper(self, from_nick: str, doc: dict) -> None:
        if not isinstance(doc.get("machines"), dict):
            return
        if not self._should_bobiverse_pull():
            return
        chair = (bobreport.digest_chair_nick(self.home) or "").strip().lower()
        if chair and from_nick.strip().lower() != chair:
            return
        mid = self._local_machine_id()
        machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
        chair_ent = machines.get(mid) if mid else None
        payload = None
        if mid and isinstance(chair_ent, dict):
            payload = bobreport.merge_payload_local_peer_ahead_of_chair(self.home, mid, chair_ent)
        bobreport.ingest_fleet_digest_pull(self.home, doc)
        if not payload:
            return
        try:
            import post_working_on as _pwo

            code = _pwo.post(payload)
            info(f"INFO bobiverse webhook POST {code} machine={mid}")
        except Exception as exc:  # noqa: BLE001
            info(f"INFO bobiverse webhook skip: {exc}")

    def _maybe_refresh_cursor_fuel(self, peer_id: str) -> None:
        """Local seat only: merge Cursor usage when Watch/POINT lack remaining_* (#70 MUST 5)."""
        local = self._local_machine_id()
        if not local or str(peer_id or "") != local:
            return
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return
        try:
            bobstat.refresh_peer_cursor_remaining(self.home, local)
        except OSError:
            pass

    def _maybe_mention_reply(self, src: str, target: str, body: str, to_channel: bool, to_me: bool) -> bool:
        """ACK when a human/worker addresses this bob-* nick. No grok.exe."""
        if getattr(self.args, "chair", False):
            return False
        if not bobtalk.is_fleet_bob_nick(self.original_nick):
            return False
        nicks = [self.live_nick, self.original_nick]
        mid = bobreport.machine_from_nick(self.original_nick) or self.original_nick
        self._maybe_refresh_cursor_fuel(mid)
        line = bobtalk.mention_reply_line(self.home, mid, nicks, src, body, to_me=to_me)
        if not line:
            return False
        if bobreport.looks_like_secret(body) or bobreport.looks_like_secret(line):
            return False
        key = (src or "").strip().lower()
        now = time.time()
        last = self._mention_last.get(key, 0.0)
        if now - last < bobtalk.MENTION_COOLDOWN_S:
            return True
        self._mention_last[key] = now
        if to_channel:
            dest = bobreport.normalize_channel(target) or self._reply_channel()
            self.send_privmsg_lines("PRIVMSG " + dest + " :" + line)
            time.sleep(FLOOD_S)
        else:
            # bob-* may still PM; workers never reach here as fleet_bob-only path.
            # If a worker seat ever hits this, whisper() rewrites to shop (FR #224).
            self.whisper(src, line)
        info(f"INFO mention-ack to={src} dest={'chan' if to_channel else 'pm'}")
        grok_talk.enqueue_mention(
            self.home,
            mid,
            self.live_nick,
            nicks,
            src,
            target,
            body,
            to_me=to_me,
            to_channel=to_channel,
            dedupe_last=self._grok_talk_dedup,
        )
        return True

    def request_shutdown(self, reason: str = ":bye", *, reconnect: bool = False) -> None:
        """PART every channel, then QUIT. Default: do not reconnect."""
        if not reconnect:
            self._no_reconnect = True
        try:
            if self.sock is not None and self.joined.is_set():
                msg = reason if reason.startswith(":") else ":" + reason
                why = msg.lstrip(":")
                for ch in self.channels:
                    self.send("PART " + ch + " :" + why)
                self.send("QUIT " + msg)
        except OSError:
            pass
        self.stop.set()

    def recv_idle_reconnect(self) -> None:
        """Deaf socket: drop it and let run_forever reconnect in-process.

        No PART/QUIT (the seat stays in its channels from the server's view
        until the TCP dies) and no process exit, so the monitor does not
        relaunch us and hammer Ergo's connect throttle.
        """
        self._last_server_rx = time.time()
        self.dead.set()
        sock = self.sock
        self.sock = None
        try:
            if sock is not None and hasattr(sock, "close"):
                sock.close()
        except Exception:
            pass

    def _seat_liveness_enabled(self) -> bool:
        if talk_seat_pid.parse_talk_seat_nick(self.original_nick) is None:
            return False
        if talk_seat_pid.seat_liveness_disabled():
            return False
        return True

    def _consume_control_quit(self) -> bool:
        reason = agent_control.consume_quit_request(self.home)
        if reason is None:
            return False
        info(f"INFO agent quit request ({reason})")
        self.request_shutdown(":control")
        return True

    def _seat_recv_stale(self) -> bool:
        if not self.joined.is_set():
            return False
        last = self._last_server_rx
        if last <= 0:
            return False
        idle_s = talk_seat_ghost.seat_recv_idle_s()
        return (time.time() - last) > idle_s

    def _seat_pong_overdue(self) -> bool:
        due = self._pong_due_at
        if due <= 0:
            return False
        return time.time() > due

    def seat_liveness_loop(self) -> None:
        interval = talk_seat_pid.seat_liveness_poll_s()
        while not self.stop.is_set():
            if self.stop.wait(timeout=interval):
                return
            if self._consume_control_quit():
                return
            if not self._seat_liveness_enabled():
                continue
            if self._seat_pong_overdue():
                info("INFO seat PONG overdue; QUIT")
                self.request_shutdown(":pong timeout")
                return
            if self._seat_recv_stale():
                info("INFO seat server idle; reconnect in place (no PART)")
                self.recv_idle_reconnect()
                return
            if talk_seat_pid.talk_seat_coordinator_gone(self.original_nick, self.home):
                info("INFO seat coordinator gone; QUIT")
                self.request_shutdown(":seat ended")
                return

    def connect(self) -> ssl.SSLSocket:
        ctx = ssl.create_default_context()
        raw = socket.create_connection((self.args.host, self.args.port), 20)
        raw.settimeout(None)
        sock = ctx.wrap_socket(raw, server_hostname=self.args.host)
        sock.settimeout(None)
        return sock

    def sasl_token(self) -> str | None:
        user = os.environ.get("BOB_IRC_SASL_USER")
        pw = os.environ.get("BOB_IRC_SASL_PASSWORD")
        if not user or not pw:
            return None
        return base64.b64encode(b"\0" + user.encode("utf-8") + b"\0" + pw.encode("utf-8")).decode("ascii")

    def sasl_on_line(self, cmd: str, args: list[str], trailing: str) -> list[str]:
        """Advance SASL. Returns lines to send. No network."""
        out: list[str] = []
        tokens = [a.lower() for a in args] + trailing.lower().split()
        if cmd == "CAP" and "ack" in tokens and "sasl" in tokens:
            self.sasl_ack.set()
            out.append("AUTHENTICATE PLAIN")
        # Ergo sends bare "AUTHENTICATE +" (no " :"); trailing-only miss → no-sasl timeout (issue #8).
        auth_chal = (trailing or (args[0] if args else "")).strip().lstrip(":")
        if cmd == "AUTHENTICATE" and auth_chal == "+":
            self.sasl_plus.set()
            tok = self.sasl_token()
            if tok:
                out.append("AUTHENTICATE " + tok)
        if cmd == "903":
            self.sasl_903.set()
            out.append("CAP END")
        if cmd in ("902", "904", "905", "906", "907"):
            self.sasl_fail.set()
            out.append("CAP END")
        return out

    def sasl_plain(self) -> bool:
        """Run PLAIN SASL. Returns True on 903 success. Issue #11: reason-tagged no-sasl."""
        if not self.sasl_token():
            info("INFO no-sasl reason=missing-creds")
            self.send("CAP END")
            return False
        self.sasl_ack.clear()
        self.sasl_plus.clear()
        self.sasl_903.clear()
        self.sasl_fail.clear()
        # Request sasl + account caps together; server ACKs what it supports (FR #230).
        self.send("CAP REQ :sasl account-notify extended-join account-tag")
        if not self.sasl_ack.wait(10):
            info("INFO no-sasl reason=cap-ack-timeout")
            self.send("CAP END")
            return False
        if not self.sasl_plus.wait(10):
            info("INFO no-sasl reason=authenticate-timeout")
            self.send("CAP END")
            return False
        if self.sasl_fail.wait(0.01):
            info("INFO no-sasl reason=sasl-numeric-fail")
            return False
        if not self.sasl_903.wait(10):
            info("INFO no-sasl reason=903-timeout")
            self.send("CAP END")
            return False
        info("INFO sasl ok")
        return True

    def handle_capa(self, src: str, body: str) -> None:
        p = wire.parse_capa_line(body)
        if p:
            info(f"INFO capa from={src}")

    def handle_moot(self, src: str, body: str) -> None:
        ml = wire.parse_moot_line(body)
        if not ml:
            return
        # IRC does not echo own PRIVMSG. Chair OPEN/FLOOR/CLOSE live on disk via CLI;
        # incoming JOIN/SAY/YIELD must load that snapshot or roster stays {chair}.
        disk = moot.load_state(self.home, ml.moot_id)
        if disk.get("id") == ml.moot_id:
            base = disk
        elif self._moot.get("id") == ml.moot_id:
            base = self._moot
        else:
            base = {}
        self._moot = moot.apply_moot(base, src, ml, self.home)
        if ml.verb == "OPEN":
            info(f"INFO moot OPEN id={ml.moot_id} chair={src}")
        elif ml.verb == "JOIN":
            info(f"INFO moot JOIN id={ml.moot_id} nick={src}")
            if ml.moot_id == bobtalk.FLEET_MOOT_ID:
                self._maybe_brief_joiner(src)
        elif ml.verb == "POINT" and (ml.text or "").startswith("BOB v1"):
            doc = bobstat.parse_bob_point(ml.text)
            if doc:
                bobstat.write_peer(self.home, doc)
                self._maybe_refresh_cursor_fuel(str(doc.get("id") or ""))
                info(f"INFO bobstat id={doc['id']} from={src}")

    def handle_file(self, src: str, body: str) -> None:
        fl = wire.parse_file_line(body)
        if not fl:
            return
        if fl.verb == "OFFER":
            name = fl.fields[-1] if fl.fields else ""
            nbytes = fl.fields[3] if len(fl.fields) > 3 else ""
            sha = fl.fields[4] if len(fl.fields) > 4 else ""
            tier = fl.fields[5] if len(fl.fields) > 5 else ""
            if not fl.file_id:
                return
            if not self.file_bags.note_offer(src, fl.file_id, name, sha, nbytes, tier):
                info(f"INFO file OFFER id={fl.file_id} ignored (duplicate)")
                return
            info(f"INFO file OFFER id={fl.file_id} name={name} bytes={nbytes}")
            extra = 0
            try:
                extra = int(nbytes or 0)
            except (TypeError, ValueError):
                extra = 0
            if filexfer.would_exceed_cap(self.home, extra=extra):
                self._file_outbox(f"FILE v1 REFUSE {fl.file_id} :disk")
            else:
                self._file_outbox(f"FILE v1 ACCEPT {fl.file_id}")
        if fl.verb == "CHUNK" and fl.chunk_b64 and fl.i and fl.n and fl.file_id:
            data = self.file_bags.add_chunk(src, fl.file_id, fl.i, fl.n, fl.chunk_b64)
            if data is not None:
                pending = self.file_bags.take_pending_done(fl.file_id)
                if pending is not None:
                    self._finish_file(fl.file_id, pending, self.file_bags.take_assembled(fl.file_id) or data)
        if fl.verb == "ABORT" and fl.file_id:
            self.file_bags.abort(fl.file_id)
            info(f"INFO file ABORT id={fl.file_id}")
        if fl.verb == "DONE" and fl.file_id:
            sha = fl.fields[1] if len(fl.fields) > 1 else ""
            data = self.file_bags.peek_assembled(fl.file_id)
            if data is None:
                self.file_bags.note_done(fl.file_id, sha)
                info(f"INFO file DONE id={fl.file_id} wait (incomplete)")
                return
            self._finish_file(fl.file_id, sha, self.file_bags.take_assembled(fl.file_id))

    def _file_outbox(self, line: str) -> None:
        with self.outbox.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _finish_file(self, fid: str, sha: str, data: bytes | None) -> None:
        if data is None:
            info(f"INFO file DONE id={fid} fail (incomplete)")
            return
        offer = self.file_bags._offers.get(fid.lower(), {})
        name = offer.get("name") or "file.bin"
        expect = offer.get("sha") or sha
        if filexfer.complete_write(self.home, fid, name, data, expect):
            info(f"INFO file DONE id={fid} ok")
        else:
            info(f"INFO file DONE id={fid} fail")

    def handle_dumb(self, src: str, body: str) -> None:
        dl = wire.parse_dumb_line(body)
        if not dl:
            return
        if dl.from_nick and dl.from_nick.lower() != src.lower():
            info("INFO DUMB prefix != from_nick, drop")
            return
        info(f"INFO dumb job id={dl.msg_id} from={src}")

    def _may_channel_auto_pong(self) -> bool:
        """bob-* ears and named sand agents (not talk seats / w-*)."""
        nick = (self.original_nick or "").strip()
        if not nick:
            return False
        if bobtalk.is_fleet_bob_nick(nick):
            return True
        low = nick.lower()
        if low.startswith("w-"):
            return False
        if talk_seat_pid.parse_talk_seat_nick(nick) is not None:
            return False
        return True

    def _channel_ping_pattern(self, body: str) -> str | None:
        """Return None (not a ping), '' (bare ping), or the selector after ping."""
        raw = (body or "").strip()
        if not raw:
            return None
        low = raw.lower()
        if low == "ping":
            return ""
        if low.startswith("ping:") or low.startswith("ping "):
            rest = raw.split(":", 1)[1].strip() if low.startswith("ping:") else raw.split(None, 1)[1].strip()
            token = (rest.split(None, 1)[0] if rest else "").strip()
            return token if token else None
        return None

    @staticmethod
    def _nick_matches_ping_selector(nick: str, selector: str) -> bool:
        """Exact, prefix, substring (unique-ish), or shell-style * ? wildcards."""
        n = (nick or "").strip().lower()
        sel = (selector or "").strip().lower().rstrip(",:;!?")
        if not n or not sel:
            return False
        if sel == n:
            return True
        if any(ch in sel for ch in "*?"):
            # shell-style: * -> .*  ? -> .
            import re
            parts = []
            for ch in sel:
                if ch == "*":
                    parts.append(".*")
                elif ch == "?":
                    parts.append(".")
                else:
                    parts.append(re.escape(ch))
            try:
                return re.fullmatch("".join(parts), n) is not None
            except re.error:
                return False
        # prefix always wins (ping bob -> bob-ionos, bob-dev1, ...)
        if n.startswith(sel):
            return True
        # substring only when selector is reasonably specific (>=3 chars)
        if len(sel) >= 3 and sel in n:
            return True
        return False

    def _channel_ping_targets_me(self, body: str) -> bool:
        """Bare ping, or ping selector that matches this seat nick."""
        sel = self._channel_ping_pattern(body)
        if sel is None:
            return False
        if sel == "":
            return True
        return any(self._nick_matches_ping_selector(n, sel) for n in self._mine_nicks())

    def _maybe_channel_pong(self, src: str, target: str, body: str) -> bool:
        """Joined-channel ping -> pong. No Grok wake.

        bob-* ears and named agents (e.g. Haitch). Matches bare ping,
        ping <nick>, ping <partial>, and ping bob-* wildcards when the
        pattern matches this seat. Talk seats stay silent. Returns before
        mention-ack / grok_talk enqueue.
        """
        if not self._may_channel_auto_pong():
            return False
        if not self._joined_channel(target):
            return False
        if (src or "").strip().lower() in self._mine_nicks():
            return False
        if not self._channel_ping_targets_me(body):
            return False
        dest = bobreport.normalize_channel(target)
        if not dest or "|" in dest:
            return False
        self.send("PRIVMSG " + dest + " :pong")
        time.sleep(FLOOD_S)
        info("INFO auto-pong")
        return True

    def _git_say(self, target: str, text: str) -> None:
        dest = bobreport.normalize_channel(target)
        if not dest or "|" in dest:
            return
        self.send("PRIVMSG " + dest + " :" + text)
        time.sleep(FLOOD_S)

    def _maybe_git_list(self, src: str, target: str, body: str, *, to_channel: bool) -> bool:
        """Chair only (FR #208 / #224): !list typed in-channel or PM → reply by PM only.

        Never post list lines in the channel (no flood). Accepts #{machine} and #bobiverse.
        """
        if not getattr(self.args, "chair", False):
            return False
        if not gitclaim.is_list_command(body):
            return False
        # In-channel: must be a joined channel (shop or bobiverse). PM also ok.
        if to_channel and not self._joined_channel(target):
            return False
        now = time.time()
        if not gitclaim.list_rate_ok(src, now):
            # FR #208 updated: one short notice, not NAK spam
            self.whisper(src, gitclaim.list_rate_notice(src, now))
            info(f"INFO git-list rate nick={src}")
            return True
        task_f, repo_f, list_all = gitclaim.parse_list_command(body)
        lines = gitclaim.format_unaccepted_list(
            self.home,
            task_filter=task_f,
            repo_filter=repo_f,
            list_all=list_all,
            now=now,
        )
        # Pace under Ergo flood/fakelag (one job line per FLOOD_S). PM only.
        for ln in lines:
            self.whisper(src, ln)
            time.sleep(FLOOD_S)
        info(f"INFO git-list pm nick={src} lines={len(lines)} from_chan={to_channel}")
        return True

    def _maybe_git_help(self, src: str, target: str, body: str, *, to_channel: bool) -> bool:
        """Chair only (FR #224 / gh-Jeeves #27): !help in-channel or PM → PM reply, no channel flood."""
        if not getattr(self.args, "chair", False):
            return False
        if not gitclaim.is_help_command(body):
            return False
        if to_channel and not self._joined_channel(target):
            return False
        now = time.time()
        if not gitclaim.help_rate_ok(src, now):
            self.whisper(src, gitclaim.help_rate_notice(src, now))
            info(f"INFO git-help rate nick={src}")
            return True
        lines = gitclaim.format_help_lines(body, asker=src)
        for ln in lines:
            self.whisper(src, ln)
            time.sleep(FLOOD_S)
        info(f"INFO git-help pm nick={src} lines={len(lines)} from_chan={to_channel}")
        return True

    def _maybe_focus_ignore(self, src: str, target: str, body: str, *, to_channel: bool) -> bool:
        """Chair only (#39 gap 3): !focus / !unfocus / !focus strict / !ignore / !unignore / !ignored.

        Replies by PM (never floods the channel). Reads are open; mutations need the owner's
        services account (AccountMap from account-tag / extended-join), see focus_ignore.may_mutate.
        """
        if not getattr(self.args, "chair", False):
            return False
        if not focus_ignore.is_focus_family(body):
            return False
        if to_channel and not self._joined_channel(target):
            return False
        if src.lower() in self._mine_nicks():
            return True
        acct = self.accounts.get(src) if self.accounts is not None else None
        try:
            lines = focus_ignore.dispatch(self.home, src, acct, body)
        except Exception as exc:  # never let a bad focus file kill the chair loop
            info(f"INFO focus-ignore error {type(exc).__name__}: {exc}"[:200])
            return True
        for ln in lines or []:
            self.whisper(src, ln)
            time.sleep(FLOOD_S)
        info(f"INFO focus-ignore nick={src} account={acct or '-'} lines={len(lines or [])}")
        return True

    def _maybe_git_claim(self, src: str, target: str, body: str) -> bool:
        """Shop claim path (FR #207 / #233): chair or bob-* ear in #{machine}.

        FR #233 / gh-Jeeves #106: bob-* ears no longer OFFER on !bored (Jeeves assigns).
        Chair path may still offer for local/legacy tests. Worker ACK in #{machine}
        marks an offered job accepted. !ACCEPT remains a no-op (legacy).
        """
        chair = bool(getattr(self.args, "chair", False))
        fleet_bob = bobtalk.is_fleet_bob_nick(self.original_nick)
        if not chair and not fleet_bob:
            return False
        if not self._joined_channel(target):
            return False
        now = time.time()
        if gitclaim.is_bored_command(body):
            if chair:
                try:
                    self._workers().on_bored(src, target)
                except Exception as exc:  # noqa: BLE001
                    info(f"WARN workers bored error {type(exc).__name__}")
            self._git_bored(src, target, now, chair=chair)
            return True
        if gitclaim.is_accept_command(body):
            self._git_accept(src, target, body)
            return True
        if gitclaim.parse_worker_ack(body):
            self._git_ack(src, target, now)
            return True
        shop = gitclaim.worker_shop_channel(src)
        if shop and bobreport.normalize_channel(target).lower() == shop:
            gitclaim.note_worker_activity(self.home, src, now)
        return False

    def _git_bored(self, src: str, target: str, now: float, *, chair: bool = False) -> None:
        # FR #233: ear must not race Jeeves — no OFFER / assign-write from bob-*.
        if not chair:
            info(f"INFO git-claim bored ear-noop nick={src} (Jeeves assigns; gh-Jeeves#106)")
            return
        gate = gitclaim.bored_gate(self.home, src, target, now)
        if gate == "ignore":
            info(f"INFO git-claim bored ignore nick={src}")
            return
        if gate == "wait":
            self._git_say(target, gitclaim.NAK_BORED_WAIT)
            info(f"INFO git-claim bored nak wait nick={src}")
            return
        if gate == "busy":
            gitclaim.note_worker_activity(self.home, src, now)
            self._git_say(target, gitclaim.NAK_BORED_BUSY)
            info(f"INFO git-claim bored nak busy nick={src}")
            return
        # #39 gap 2: focus-ordered, one wire line "<nick>: FR|MRB|UAT owner/repo#N url".
        # Acceptance is still the seat's ACK (FR #207).
        status, job = gitclaim.offer_focus_top(
            self.home, src, bobreport.normalize_channel(target), now=now
        )
        if status == "ok" and isinstance(job, dict):
            gitclaim.note_worker_activity(self.home, src, now)
            line = gitclaim.format_assign_line(src, job)
            self._git_say(target, line)
            info(f"INFO git-claim bored offered {line} nick={src}")
            return
        if status == "empty":
            gitclaim.note_worker_activity(self.home, src, now)
            self._git_say(target, gitclaim.format_nothing_queued(src))
            info(f"INFO git-claim bored empty nick={src}")
            return
        info(f"INFO git-claim bored offer failed nick={src}")

    def _git_ack(self, src: str, target: str, now: float) -> None:
        """ACK in #{machine} marks the offered job accepted on the webhook mirror."""
        shop = gitclaim.worker_shop_channel(src)
        if shop is None or bobreport.normalize_channel(target).lower() != shop:
            return
        status, job = gitclaim.accept_offered(self.home, src, bobreport.normalize_channel(target))
        if status == "ok" and isinstance(job, dict):
            gitclaim.note_worker_activity(self.home, src, now)
            line = gitclaim.format_claimed(job)
            if getattr(self.args, "chair", False):
                try:
                    self._workers().on_ack(src, target, shop_listen.activity_description(job))
                except Exception as exc:  # noqa: BLE001
                    info(f"WARN workers ack error {type(exc).__name__}")
            self._git_say(target, f"{src}: accepted {line}")
            info(f"INFO git-claim ack accepted {line} nick={src}")
            return
        info(f"INFO git-claim ack no offer nick={src}")

    def _git_accept(self, src: str, target: str, body: str) -> None:
        """Legacy !ACCEPT is a no-op; use ACK after !BORED offer (FR #207)."""
        del target, body
        info(f"INFO git-claim accept noop nick={src}")

    def _maybe_shop_listen(self, src: str, target: str, body: str) -> bool:
        """FR #211: chair records ACK/DONE in #{machine}; fires activity webhook. No channel reply."""
        if not getattr(self.args, "chair", False):
            return False
        if not shop_listen.parse_shop_job_line(body):
            return False
        if not shop_listen.is_shop_worker_nick(src, target):
            return False
        briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick or "Jeeves"
        try:
            result = shop_listen.handle_shop_worker_line(
                self.home,
                nick=src,
                channel=target,
                body=body,
                briefer=briefer,
            )
        except Exception as exc:
            info(f"INFO shop-listen error {type(exc).__name__}")
            return True
        if not result.get("handled"):
            return False
        verb = result.get("verb") or ""
        status = result.get("status") or ""
        act = result.get("activity")
        try:
            if verb == "ACK" and status in ("ok", "duplicate") and act:
                self._workers().on_ack(src, target, act)
            elif verb in ("DONE", "NACK", "GIVEUP"):
                self._workers().on_done(src, target)
        except Exception as exc:  # noqa: BLE001
            info(f"WARN workers {verb} error {type(exc).__name__}")
        info(
            f"INFO shop-listen {verb} status={status} nick={src} "
            f"activity={act!r} webhook={result.get('webhook')}"
        )
        # Never PRIVMSG the shop channel (FR #211).
        return True

    def handle_privmsg(self, prefix: str, target: str, body: str) -> None:
        src = prefix.split("!", 1)[0].lstrip(":")
        tgt_l = target.lower()
        to_channel = self._joined_channel(target)
        to_me = tgt_l in self._mine_nicks()
        if to_channel:
            self._note_call_channel(target)
        if not to_channel and not to_me:
            return
        if to_channel and self._maybe_channel_pong(src, target, body):
            return
        if self._maybe_git_list(src, target, body, to_channel=to_channel):
            return
        if self._maybe_git_help(src, target, body, to_channel=to_channel):
            return
        if self._maybe_focus_ignore(src, target, body, to_channel=to_channel):
            return
        if to_channel and self._maybe_shop_listen(src, target, body):
            return
        if to_channel and self._maybe_git_claim(src, target, body):
            return
        if to_me:
            self._mark_pm_open(src)
            if src.lower() not in self._mine_nicks():
                pulled = self._digest_asm.feed(src, body)
                if pulled is not None:
                    self._on_digest_whisper(src, pulled)
                    return
        if self._handle_register_command(src, body):
            return
        if bobtalk.parse_recycle_command(body):
            if getattr(self.args, "chair", False):
                self._handle_recycle_command(src, body)
            else:
                self._handle_bob_local_recycle_command(src, body)
            return
        if self._maybe_execute_recycle_wire(src, body):
            return
        if bobtalk.parse_bobiverse_command(body):
            self._answer_bobiverse(src, body)
            return
        if bobreport.parse_report_command(body):
            self._handle_report(src, to_channel, body)
            return
        if not to_channel:
            self._maybe_mention_reply(src, target, body, to_channel=False, to_me=True)
            return
        if to_channel and self._is_briefer():
            ch = bobreport.normalize_channel(target)
            if ch.lower() != bobreport.FLEET_CHANNEL.lower():
                if bobreport.parse_working_on_shop_line(body):
                    briefer = bobtalk.briefer_nick(self._fleet_moot_state()) or self.live_nick
                    out = bobreport.ingest_working_on_shop(self.home, src, body, briefer)
                    if out.ok and out.actions:
                        worker = bobreport.parse_worker_nick(src)
                        key = f"{worker[0]}:{worker[1]}" if worker else src
                        self._emit_presence(out, "working_on", key)
                    return
        if not to_channel:
            return
        pk = seal.parse_agpk_line(body)
        if pk is not None:
            result = seal.tofu_pin(self.peers, src, pk)
            if result == "pinned":
                seal.save_peers(self.peers)
                info(f"INFO peer {src} AGPK pinned")
            elif result == "mismatch":
                info(f"INFO peer {src} AGPK mismatch (ignored)")
            return
        parsed = seal.parse_seal_line(body)
        if parsed is None:
            self.handle_capa(src, body)
            self.handle_moot(src, body)
            self.handle_file(src, body)
            self.handle_dumb(src, body)
            self._maybe_mention_reply(src, target, body, to_channel=True, to_me=False)
            return
        if parsed.version == 2 and parsed.from_nick and parsed.from_nick.lower() != src.lower():
            info("INFO SEAL prefix != from_nick, drop")
            return
        mine = {self.original_nick.lower(), self.live_nick.lower()}
        if parsed.to_nick.lower() not in mine:
            return
        if parsed.version != 2:
            info(f"INFO SEAL {parsed.msg_id} v1 ignored")
            return
        payload = self.fragments.add(parsed)
        if payload is None:
            return
        if self.ident is None:
            info(f"INFO SEAL {parsed.msg_id} dropped (no identity)")
            return
        try:
            blob = seal.b64d(payload)
            if parsed.version == 2:
                from_nick = parsed.from_nick or src
                pin = self.peers.get(from_nick.lower(), {}).get("pk")
                if not pin:
                    info(f"INFO SEAL {parsed.msg_id} dropped (no AGPK pin for {from_nick})")
                    return
                pt = seal.open_bytes_v2(
                    blob, self.ident, self.chan, parsed.to_nick, from_nick, parsed.msg_id, pin
                )
            else:
                return
        except Exception as e:
            info(f"INFO SEAL {parsed.msg_id} decrypt failed {type(e).__name__}")
            return
        if self._take_airc_file(parsed.msg_id, pt):
            return
        dest = self.inbox / f"{parsed.msg_id}.bin"
        if dest.exists():
            info(f"INFO SEAL {parsed.msg_id} inbox id exists, skip write")
            return
        dest.write_bytes(pt)
        protect.protect_path(dest)
        info(f"INFO SEAL {parsed.msg_id} -> inbox ({len(pt)} bytes)")

    def _take_airc_file(self, msg_id: str, pt: bytes) -> bool:
        """Consume AIRC-FILE v1 plaintext into files/complete/. True = not an inbox SEAL."""
        if not pt.startswith(b"AIRC-FILE v1"):
            return False
        env = filexfer.decode_airc_file(pt)
        if env is None:
            info(f"INFO file DONE id={msg_id} fail")
            return True
        offer = self.file_bags._offers.get(msg_id.lower(), {})
        if offer:
            if offer.get("sha") and str(offer["sha"]).lower() != env["sha256"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
            try:
                offered_n = int(offer["bytes"]) if offer.get("bytes") is not None else None
            except (TypeError, ValueError):
                offered_n = None
            if offered_n is not None and offered_n != env["bytes"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
            if offer.get("name") and offer["name"] != env["name"]:
                info(f"INFO file DONE id={msg_id} fail")
                return True
        if filexfer.complete_write(
            self.home, msg_id, env["name"], env["data"], env["sha256"], expect_len=env["bytes"]
        ):
            info(f"INFO file DONE id={msg_id} ok")
        else:
            info(f"INFO file DONE id={msg_id} fail")
        return True

    def reader(self) -> None:
        assert self.sock is not None
        buf = b""
        try:
            while not self.stop.is_set():
                data = self.sock.recv(4096)
                if not data:
                    return
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    t = line.decode("utf-8", "replace").rstrip("\r")
                    self._last_server_rx = time.time()
                    debug_log(self.debug, t)
                    if t.startswith("PING "):
                        self._pong_due_at = time.time() + talk_seat_ghost.pong_grace_s()
                        try:
                            self.send("PONG " + t[5:])
                            self._pong_due_at = 0.0
                        except OSError:
                            pass
                        continue
                    # FR #230: strip IRCv3 tags; keep raw line in irc.log (debug_log above).
                    tags: dict[str, str] = {}
                    wire = t
                    try:
                        from account_map import account_from_tags, parse_message_tags

                        tags, wire = parse_message_tags(t)
                    except Exception:
                        account_from_tags = None  # type: ignore[assignment]
                    prefix = ""
                    rest = wire
                    if wire.startswith(":"):
                        prefix, _, rest = wire[1:].partition(" ")
                    parts = rest.split(" ")
                    cmd = parts[0] if parts else ""
                    trailing = wire.split(" :", 1)[1] if " :" in wire else ""
                    # Track services account for nick (account-tag / ACCOUNT / extended-join).
                    if self.accounts is not None:
                        who = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if cmd == "ACCOUNT" and who:
                            acct = (parts[1] if len(parts) > 1 else trailing) or ""
                            acct = acct.lstrip(":")
                            self.accounts.set(who, None if acct in ("", "*") else acct)
                            try:
                                self.accounts.save(self.home / "accounts.json")
                            except Exception:
                                pass
                        elif cmd == "JOIN" and who:
                            # extended-join: JOIN #chan account :realname
                            acct = None
                            if account_from_tags is not None:
                                acct = account_from_tags(tags)
                            if acct is None and len(parts) >= 3 and not parts[2].startswith("#"):
                                # nick JOIN #chan account :gecos
                                maybe = parts[2].lstrip(":")
                                if maybe and maybe != "*" and not maybe.startswith("#"):
                                    acct = maybe
                            if acct:
                                self.accounts.set(who, acct)
                                try:
                                    self.accounts.save(self.home / "accounts.json")
                                except Exception:
                                    pass
                        elif cmd == "NICK" and who:
                            new = (trailing or (parts[1] if len(parts) > 1 else "")).lstrip(":")
                            if new:
                                self.accounts.rename(who, new)
                                try:
                                    self.accounts.save(self.home / "accounts.json")
                                except Exception:
                                    pass
                        elif cmd == "QUIT" and who:
                            self.accounts.clear_nick(who)
                            try:
                                self.accounts.save(self.home / "accounts.json")
                            except Exception:
                                pass
                        elif cmd == "PRIVMSG" and who and account_from_tags is not None:
                            acct = account_from_tags(tags)
                            if acct:
                                self.accounts.set(who, acct)
                                try:
                                    self.accounts.save(self.home / "accounts.json")
                                except Exception:
                                    pass
                    if not self.ready.is_set() and cmd in REG_FAIL_CMDS:
                        detail = trailing.strip() or (parts[1] if len(parts) > 1 else "")
                        info(f"INFO reg {cmd} {detail}".strip()[:220])
                        if cmd == "ERROR" and is_connect_throttle(detail):
                            self._throttled = True
                    if cmd == "NOTICE" and prefix.split("!", 1)[0].lower() == "chanserv":
                        try:
                            self._on_chanserv_notice(trailing)
                        except Exception as exc:  # never kill the reader over a mirror bug
                            info(f"INFO chanserv-sync notice error {type(exc).__name__}")
                    if cmd in ("381", "464", "491", "481", "221") or (cmd == "MODE" and len(parts) > 2 and not parts[1].startswith("#")):
                        self._on_oper_numeric(cmd, parts, trailing)
                    if cmd in ("353", "MODE"):
                        self._on_chair_channel_line(cmd, parts, trailing)
                    if cmd in ("353", "366", "JOIN", "PART", "KICK", "QUIT", "NICK", "ACCOUNT", "MODE", "330", "318") or (
                        cmd == "PRIVMSG" and "account" in tags
                    ):
                        self._chair_wire(cmd, parts, trailing, prefix, tags)
                    if cmd == "001":
                        self.ready.set()

                        self._throttle_n = 0

                    if cmd == "005" or cmd == "RPL_ISUPPORT":
                        # ISUPPORT tokens in parts[1:] until :trailing
                        for tok in parts[1:]:
                            if tok.startswith(":"):
                                break
                            if tok.upper().startswith("LINELEN="):
                                try:
                                    self._linelen = max(200, int(tok.split("=", 1)[1]))
                                except ValueError:
                                    pass
                    if cmd == "417":
                        # Ergo: line too long — message was dropped; never log full body/secrets
                        who = parts[1] if len(parts) > 1 else "?"
                        raw_tr = (trailing or "").strip().replace("\n", " ")
                        # Fixed short label only — do not echo server trailing (may carry payload)
                        prev = "Line too long"
                        if raw_tr.lower().startswith("line too long"):
                            prev = "Line too long"
                        info(f"INFO 417 line too long nick={who} preview={prev}")


                    if cmd == "482":
                        # ERR_CHANOPRIVSNEEDED: shop KICK/MODE without op (Ergo: creator-only op).
                        info(f"INFO shop-op 482 not channel operator: {' '.join(parts[2:4])}"[:200])

                    if cmd == "JOIN":
                        ch = parts[1].lstrip(":") if len(parts) > 1 else ""
                        if not ch and trailing:
                            ch = trailing.lstrip(":")
                        joiner = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if joiner:
                            for one in bobreport.expand_join_channels(ch):
                                self.handle_join(joiner, one)
                    if cmd == "PART":
                        ch = parts[1].lstrip(":") if len(parts) > 1 else ""
                        if not ch and trailing:
                            ch = trailing
                        who = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if who:
                            self.handle_part(who, ch)
                    if cmd == "QUIT":
                        who = prefix.split("!", 1)[0].lstrip(":") if prefix else ""
                        if who:
                            self.handle_quit(who)
                    if cmd in ("433", "432"):
                        if self.live_nick == self.original_nick:
                            # Fleet Bob-* ears: do not silently fall back to _l when the
                            # reserved nick is owned by another NickServ account (issue #11).
                            if (self.original_nick or "").lower().startswith("bob-"):
                                self._nickname_reserved = True
                                info(
                                    "INFO NICKNAME_RESERVED abort nick="
                                    + self.original_nick
                                    + " - fix home\\nickserv.password or oper SAREGISTER"
                                )
                            elif bobreport.parse_worker_nick(self.original_nick):
                                self.live_nick = self.original_nick + "_"
                                self.send("NICK " + self.live_nick)
                                info(f"INFO nick -> {self.live_nick} (still accept {self.original_nick})")
                            else:
                                self.live_nick = self.original_nick + "_l"
                                self.send("NICK " + self.live_nick)
                                info(f"INFO nick -> {self.live_nick} (still accept {self.original_nick})")
                    # Ergo: FAIL NICK NICKNAME_RESERVED <nick> :… — surface before NO 001 (issue #8).
                    if cmd == "FAIL":
                        info(
                            "INFO FAIL "
                            + " ".join(parts[1:4] + ([trailing] if trailing else []))[:220]
                        )
                        joined = " ".join(parts[1:4] + ([trailing] if trailing else [])).lower()
                        if "nickname_reserved" in joined or "nickname is reserved" in joined:
                            self._nickname_reserved = True
                    if trailing and "nickname is reserved" in trailing.lower():
                        self._nickname_reserved = True
                        info(f"INFO NICKNAME_RESERVED {trailing.strip()[:180]}")
                    for line in self.sasl_on_line(cmd, parts[1:], trailing):
                        self.send(line)
                    if cmd == "PRIVMSG" and " :" in wire:
                        target = parts[1].lstrip(":") if len(parts) > 1 else ""
                        self.handle_privmsg(prefix, target, wire.split(" :", 1)[1])
        except OSError:
            return
        finally:
            self.dead.set()

    def _drain_outbox_path(self, path: Path) -> list[str]:
        if self.sock is None or not path.exists():
            return []
        last = load_outbox_pos(path)
        lines, new_last = take_outbox_lines(path, last, max_lines=OUTBOX_LINES_PER_TICK)
        sent: list[str] = []
        gate_fleet = bobreport.chair_mode_active(self.home)
        for line in lines:
            # FR #226: re-normalize (BOM / pre-wrapped) before classify
            kind, norm = normalize_outbox_line(line)
            if kind == "empty":
                continue
            line = norm
            if gate_fleet and bobreport.outbox_line_spam_for_fleet_channel(line, default_channel=self.chan):
                continue
            op = shop_ops.raw_op_line(line, self.original_nick)
            if kind == "privmsg" or line.upper().startswith("PRIVMSG "):
                wire = self.send_privmsg_lines(line)
                sent.extend(wire)
                time.sleep(FLOOD_S)
            elif op:
                # bob-* shop ops (A23): KICK / MODE / NAMES on own #{machine}, raw.
                self.send(op)
                info(f"INFO shop-op sent {op.split(' :', 1)[0]}")
                time.sleep(FLOOD_S)
            else:
                self.say(line)
                sent.append(line)
        if new_last != last:
            save_outbox_pos(path, new_last)
        return sent

    def drain_outbox_once(self) -> list[str]:
        """Send complete unread outbox lines. Offset persisted; restart does not skip JOIN."""
        if not getattr(self.args, "chair", False):
            try:
                grok_talk.drain_completions_to_outbox(self.home, outbox=self.outbox)
            except OSError:
                pass
        if self.sock is None:
            return []
        sent = self._drain_outbox_path(self.outbox)
        if getattr(self.args, "chair", False):
            chair_out = bobreport.fleet_digest_home(self.home) / "chair-outbox.txt"
            sent.extend(self._drain_outbox_path(chair_out))
        return sent

    def outbox_loop(self, gen: int | None = None) -> None:
        while not self.stop.is_set() and not self.dead.is_set():
            if gen is not None and gen != self._outbox_gen:
                return
            if not self.joined.wait(timeout=1):
                continue
            if gen is not None and gen != self._outbox_gen:
                return
            try:
                # FR #68: ChanServ sync / SAMODE before outbox drain so a migrated
                # backlog cannot starve +o for tens of minutes (drain is also capped).
                self._maybe_chanserv_sync()
                self._ensure_chan_ops()
                self._chan_privs_tick()
                self.drain_outbox_once()
                self._maybe_bobiverse_pull()
                self._maybe_depart_request()
                self._maybe_prune_talk_seat_ghosts()
            except OSError:
                return
            time.sleep(1)

    def _abort_gate(self, gate: str) -> None:
        info(f"INFO {gate}")
        raise TimeoutError(gate)

    def session(self) -> None:
        self.ready.clear()
        self.joined.clear()
        self.dead.clear()
        self._nickname_reserved = False
        self.live_nick = self.original_nick
        self._pending_joins = {c.lower() for c in self.channels}
        self._chair_reset_session()
        if getattr(self.args, "chair", False):
            self._privs().announce()      # created here, before the reader/outbox threads exist
        self._outbox_gen += 1
        gen = self._outbox_gen
        info(
            f"INFO connecting {self.args.host}:{self.args.port} "
            f"nick={self.live_nick} home={self.home}"
        )
        self.sock = self.connect()
        threading.Thread(target=self.reader, daemon=True).start()
        threading.Thread(target=self.outbox_loop, args=(gen,), daemon=True).start()
        if self._seat_liveness_enabled():
            threading.Thread(target=self.seat_liveness_loop, daemon=True).start()
        pw = (self.args.password or os.environ.get("BOB_IRC_PASSWORD") or "").strip()
        if pw:
            self.send("PASS " + pw)
        self.send("CAP LS 302")
        # Issue #11: when SASL creds exist, authenticate BEFORE NICK so Ergo
        # reserved Bob-* nicks are claimed by the owning NickServ account.
        want_sasl = bool(self.sasl_token())
        if want_sasl:
            sasl_ok = self.sasl_plain()
            self.send("NICK " + self.live_nick)
            self.send(f"USER {self.live_nick} 0 * :{self.args.realname}")
            if not sasl_ok:
                # Give FAIL/NICKNAME_RESERVED a moment to arrive, then abort.
                time.sleep(1.0)
                if self._nickname_reserved or (self.original_nick or "").lower().startswith("bob-"):
                    self._abort_gate("NICKNAME_RESERVED")
        else:
            self.send("NICK " + self.live_nick)
            self.send(f"USER {self.live_nick} 0 * :{self.args.realname}")
            self.sasl_plain()
        if self._nickname_reserved and (self.original_nick or "").lower().startswith("bob-"):
            self._abort_gate("NICKNAME_RESERVED")
        if not self.ready.wait(30):
            self._abort_gate("NO 001")
        time.sleep(1)
        # Ergo default-usermode is +i (LUSERS: "0 users and N invisible").
        # Halloy nick lists that use WHO then omit flamingos even in-channel.
        self.send("MODE " + self.live_nick + " -i")
        self._chair_oper_on_connect()
        # Per-channel JOIN (more reliable than comma-join on some paths / ionos shop).
        for ch in self.channels:
            self.send("JOIN " + ch)
        if not self.joined.wait(30):
            self._abort_gate("NO JOIN")
        # FR #313: bob-* REGISTER #{machine} with ChanServ (founder persists).
        self._maybe_register_shop_chanserv()
        mid = self._local_machine_id()
        if mid:
            self._maybe_refresh_cursor_fuel(mid)
        if self.args.hello:
            self.say(self.args.hello)
        if self.args.announce_key:
            if self.ident is None:
                info("INFO no identity; skip AGPK")
            else:
                self.say("AGPK v1 " + self.ident["pk"])
        info(f"INFO joined {','.join(self.channels)} as {self.live_nick}")
        self._last_server_rx = time.time()
        while not self.stop.is_set() and not self.dead.wait(timeout=1):
            if self._consume_control_quit():
                break

    def run_forever(self) -> None:
        backoff = 1.0
        attempt = 0
        cap = reconnect_cap()
        while not self.stop.is_set():
            try:
                self.session()
                backoff = 1.0
                attempt = 0
            except TimeoutError:
                pass
            except Exception as e:
                info(f"INFO session end {type(e).__name__}")
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass
            self.sock = None
            if self._no_reconnect:
                info("INFO reconnect skipped (graceful quit)")
                return
            attempt += 1
            if cap is not None and attempt >= cap:
                info(f"INFO reconnect stopped (BOB_IRC_RECONNECT_MAX={cap})")
                return
            delay = backoff + random.uniform(0, 1)
            if getattr(self, "_throttled", False):
                self._throttled = False
                self._throttle_n = getattr(self, "_throttle_n", 0) + 1
                delay = throttle_delay_s(self._throttle_n) + random.uniform(0, 5)
                info(f"INFO connect throttled n={self._throttle_n}; wait {delay:.0f}s")
            info(f"INFO reconnect attempt={attempt} in {delay:.1f}s (backoff cap 60s)")
            time.sleep(delay)
            backoff = min(60.0, backoff * 2)


def clean_crashed_priors(nick: str, home: str, *, once: bool) -> None:
    """Hard-kill hung same-nick / same-home priors before the first connect.

    Once per process, not on reconnect, so a listen started afterwards stays.
    --once and BOB_IRC_SKIP_PRIOR_CLEAN=1 skip (tests). No command lines logged.
    """
    if once:
        return
    flag = (os.environ.get("BOB_IRC_SKIP_PRIOR_CLEAN") or "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return
    import prior_irc

    # Talk-seat / worker listens are started by the launcher after this process.
    # Only a bob-* builder sweeps irc_listen here (no listen is spawned after it).
    result = prior_irc.clean_priors(
        nick,
        home,
        self_pid=os.getpid(),
        include_listens=prior_irc.is_bob_builder_nick(nick),
    )
    if not result.scanned:
        info("INFO prior-clean aborted connect")
        raise SystemExit(1)


def main() -> None:
    import signal

    p = argparse.ArgumentParser(description="agentic TLS IRC")
    p.add_argument("--host", default="irc.ntsa.uk")
    p.add_argument("--port", type=int, default=6697)
    p.add_argument("--password", default="", help="IRC PASS (or env BOB_IRC_PASSWORD)")
    p.add_argument("--nick", required=True)
    p.add_argument(
        "--channel",
        default="",
        help="seed channel (required unless --chair; chair defaults to bobiverse)",
    )
    p.add_argument("--home", default="", help="BOB_HOME (required if two nicks on one box)")
    p.add_argument("--realname", default="bobiverse")
    p.add_argument("--outbox", default="")
    p.add_argument("--hello", default="")
    p.add_argument("--announce-key", action="store_true")
    p.add_argument("--once", action="store_true", help="no reconnect (tests)")
    p.add_argument(
        "--chair",
        action="store_true",
        help="digest chair (Jeeves): JOIN #bobiverse + every #{machine}; webhook digest + public GET",
    )
    p.add_argument(
        "--auto-nick",
        action="store_true",
        help="talk seat: set --nick suffix to irc_agent PID (env self/agent= or coordinator.pid)",
    )
    args = p.parse_args()
    args.nick = chan_privs.clean_nick(args.nick)          # a BOM from a config file must never reach NICK / MODE
    args.channel = chan_privs.clean(args.channel)
    if not str(args.channel or "").strip():
        if args.chair:
            args.channel = "bobiverse"
        else:
            p.error("--channel is required unless --chair")
    home = (args.home or os.environ.get("BOB_HOME") or "").strip()
    seat_pid = talk_seat_pid.resolve_seat_pid(home or None, self_pid=os.getpid())
    if args.auto_nick:
        if seat_pid is None:
            info(
                "INFO --auto-nick requires BOB_IRC_SEAT_PID (or self) or coordinator.pid agent="
            )
            sys.exit(2)
        args.nick = talk_seat_pid.auto_talk_seat_nick(args.nick, seat_pid)
    err = None
    if talk_seat_pid.parse_talk_seat_nick(args.nick):
        if seat_pid is None:
            err = (
                "INFO talk-seat nick requires BOB_IRC_SEAT_PID (or self) or coordinator.pid agent="
            )
        else:
            err = talk_seat_pid.check_nick_seat_pid(args.nick, seat_pid)
        if err and talk_seat_pid.watch_seat_host_ok(args.nick, home or None):
            info("INFO talk-seat nick matches live watch-seat monitor (coordinator seat=)")
            err = None
    if err:
        info(err)
        sys.exit(2)
    # FR #238: warn once when coordinator seat= is not a monitor-looking process.
    if home:
        try:
            warn = talk_seat_pid.warn_if_coordinator_not_monitor(home)
            if warn:
                info(f"WARN {warn}")
        except Exception as e:  # pragma: no cover
            info(f"WARN coordinator check skipped {type(e).__name__}")
    # FR #213: warn (do not exit) when service tree is off main or has a fresh stash.
    try:
        import live_tree_guard

        live_tree_guard.check_and_report(
            home=home or None,
            role="irc_agent",
            log=info,
            mark_start=True,
        )
    except Exception as e:  # pragma: no cover - never block connect on guard bugs
        info(f"WARN live-tree guard skipped {type(e).__name__}")
    clean_crashed_priors(args.nick, home, once=bool(args.once))
    c = Client(args)

    def _stop(*_a: object) -> None:
        c.request_shutdown(":signal")

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    if args.once:
        try:
            c.session()
        except TimeoutError:
            sys.exit(1)
        return
    c.run_forever()


if __name__ == "__main__":
    main()
