#!/usr/bin/env python3
"""Shop-channel digest + public HTTP digest reader (issue #174). !bobiverse removed."""
from __future__ import annotations

import contextlib
import copy
import functools
import json
import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import bobstat
import bobtalk
import registered_machines

REPORT_CMD = "!report"
REPORT_GONE = "ERR report gone — use callback or GET /bob/v1/report"
NO_MACHINE = "ERR no such machine"
DEFAULT_DIGEST_URL = "https://irc.ntsa.uk/bob/v1/report"
DIGEST_URL_ENV = "BOB_DIGEST_URL"
BOBIVERSE_GONE = "ERR !bobiverse gone — GET https://irc.ntsa.uk/bob/v1/report"
DIGEST_PREFIX = "BOB DIGEST v1 "
MAX_DIGEST_LINE = 350
FLEET_CHANNEL = "#bobiverse"
ACTION_COOLDOWN_S = 30.0
DISCONNECT_DEDUPE_S = 30.0
# LEGACY aliases (#42): old short/handle -> current machine name. Never the roster.
ID_ALIASES = {
    "dev1": "ce-priority-dev1",
    "ce-priority-dev1": "ce-priority-dev1",
}
# #79: the ionos box was renamed; its old #ionos channel is still ChanServ-registered, so the roster mirror
# carries BOTH ids. These are folded into the real machine in the DIGEST ONLY (roster_machine_ids / machines /
# cursor_pools). Seat nicks and channel membership (``ionos-<pid>`` in #ionos) are deliberately untouched.
DIGEST_ID_FOLD: dict[str, str] = {
    "ionos": "win-mpre8vi4u6u",
    "dev1": "ce-priority-dev1",
}

# LEGACY aliases ONLY (#42): old ``bob-<alias>`` nicks and ``w-<short>-<pid>`` worker nicks
# resolve to a machine name. They never define the roster - the roster is the ChanServ
# mirror in registered-machines.json (registered_machines.sync_from_chanserv).
NICK_TO_MACHINE: dict[str, str] = {
    "bob-dev1": "ce-priority-dev1",
    "bob-ionos": "win-mpre8vi4u6u",
}

SHORT_ID: dict[str, str] = {
    "flamingo": "fl",
    "marchhare": "mh",
    "win-mpre8vi4u6u": "io",  # legacy w-io-<pid> worker nicks
    "ce-priority-dev1": "d1",
}
SHORT_TO_MACHINE = {v: k for k, v in SHORT_ID.items()}


def roster_machine_ids(home: Path | None = None, *, fold: bool = True) -> tuple[str, ...]:
    """Machine ids = the ChanServ mirror (registered-machines.json). No hardcoded fallback.

    Pure file read (cached by the chair's periodic ``ChanServ LIST`` sync, see
    ``registered_machines.sync_from_chanserv``) so the HTTP digest path never talks to IRC.
    An empty/missing registry is an EMPTY roster, not a bootstrap fleet.

    ``home`` may be the chair home (``~/.jeeves``); the ChanServ mirror lives in the digest
    home (``BOB_DIGEST_HOME`` / ``~/.bobiverse``) — FR #69.
    """
    if home is None:
        home = _default_digest_home()
    elif home is not None:
        home = fleet_digest_home(Path(home))
    if home is not None:
        reg = registered_machines.load_registered(Path(home))
        if reg:
            if not fold:
                return tuple(sorted(reg))
            return tuple(sorted({fold_machine_id(m) for m in reg}))     # #79: alias ids never appear twice
    return ()


def fold_machine_id(raw: object) -> str:
    """Canonical machine id: legacy aliases (``ID_ALIASES``) folded in; unknown ids lower-cased as-is."""
    s = str(raw or "").strip().lstrip("#").lower()
    s = DIGEST_ID_FOLD.get(s, s)
    return normalize_machine_id(s) or s


def is_alias_machine_id(raw: object) -> bool:
    """True for a legacy alias key (``ionos``, ``dev1``) whose canonical id differs."""
    s = str(raw or "").strip().lstrip("#").lower()
    return bool(s) and DIGEST_ID_FOLD.get(s, s) != s


def _default_digest_home() -> Path | None:
    env_home = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if env_home:
        return Path(env_home)
    prof = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
    if prof:
        cand = Path(prof) / ".bobiverse"
        if cand.is_dir():
            return cand
    return None


def is_roster_machine(home: Path | None, mid: str) -> bool:
    m = normalize_machine_id(mid) or ""
    if not m:
        return False
    m = fold_machine_id(m)      # #79: a legacy bob-ionos still reports as its real machine
    ids = set(roster_machine_ids(home))
    return m in ids


def _parse_iso_ts(raw: object) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _period_rolled(existing_end: object, incoming_end: object) -> bool:
    """True when incoming period_end is a new billing window vs stored."""
    inc = _parse_iso_ts(incoming_end)
    if inc is None:
        return False
    ex = _parse_iso_ts(existing_end)
    if ex is None:
        return True
    if inc != ex:
        # Newer or different window → allow replace (incl. 100% after reset)
        return True
    # Same end: if that end is already in the past and incoming still claims it, not a roll
    return False


def _period_expired(end: object, now: datetime | None = None) -> bool:
    """True when ``end`` parses and is at/before ``now`` (#40: the period has ended).

    Unparseable / missing -> False (unknown clock is not evidence of expiry).
    """
    dt = _parse_iso_ts(end)
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return dt <= ref


CURSOR_SPENDING_POOLS: tuple[tuple[str, str], ...] = (
    ("cursor-models", "Cursor Models"),
    ("other-models", "Other Models"),
    # FR #663: storage id stays grok-weekly; cursor-grok-chat is the preferred alias
    # so readers do not confuse Cursor Sand with xAI weekly.
    ("grok-weekly", "Grok chat (Cursor)"),
    ("on-demand", "On-demand"),
)
CURSOR_POOL_IDS = frozenset(pid for pid, _ in CURSOR_SPENDING_POOLS)
CURSOR_POOL_LABEL_BY_ID = dict(CURSOR_SPENDING_POOLS)
_CURSOR_POOL_ID_ALIASES: dict[str, str] = {
    "cursor_models": "cursor-models",
    "cursor_models_remaining": "cursor-models",
    "low cost models": "cursor-models",
    "low-cost-models": "cursor-models",
    "auto": "cursor-models",  # bob wire id for the Cursor Models bar
    "high cost models": "other-models",
    "high-cost-models": "other-models",
    "other_models": "other-models",
    "grok chat": "grok-weekly",
    "grok-chat": "grok-weekly",
    "grok_chat": "grok-weekly",
    "grok_weekly": "grok-weekly",
    "cursor-grok-chat": "grok-weekly",  # FR #663 preferred name -> storage id
    "sand": "grok-weekly",
    "on_demand": "on-demand",
}
_XAI_SEAT_LABELS = frozenset({"smart catalogue", "club madeira", "ntsa"})
_PCENT_KEYS_BY_POOL: dict[str, tuple[str, ...]] = {
    "cursor-models": (
        "cursor-models",
        "cursor_models",
        "cursor_models_remaining",
        "low cost models",
        "low-cost-models",
    ),
    "other-models": ("other-models", "other_models", "high cost models", "high-cost-models"),
    "grok-weekly": (
        "grok-weekly",
        "grok_weekly",
        "grok-chat",
        "grok_chat",
        "grok chat",
        "sand",
        "cursor-grok-chat",
    ),
    "on-demand": ("on-demand", "on_demand"),
}
# #40: pcent keys that follow the Grok weekly clock but are not Cursor pools.
_GROK_WEEKLY_EXTRA_PCENT_KEYS = ("grok-build",)
_MERGE_PEER_FIELDS = (
    "weekly",
    "cursor_label",
    "cursor_period_end",
    "jobs",
    "repo",
    "sha",
    "model",
    "fuel",
    "lastSeen",
    "running",
    "queued",
    "period_end",
    "reset",
    "kind",
    "cur",
    "pcent",
    "overage_gbp",
    # #60: overspend amount + state and the Sand (grok-chat) weekly reset, per machine.
    "overage_usd",
    "overspend_state",
    "on_demand_used_cents",
    "on_demand_limit_cents",
    "on_demand_remaining_pct",
    "sand_period_end",
)
_TRAY_MACHINE_EXPORT_KEYS = (
    "id",
    "nick",
    "shop",
    "online",
    "status",
    "working_on",
    "workers",
    "weekly",
    "period_end",
    "reset",
    "lastSeen",
    "running",
    "queued",
    "jobs",
    "pcent",
    "uptime_since",
    "fuel",
    "model",
    "repo",
    "sha",
    "cursor_label",
    "cursor_period_end",
    "cursor_pools",
    "kind",
    "cur",
    "overage_gbp",
    "overage_usd",
    "overspend_state",
    "on_demand_used_cents",
    "on_demand_limit_cents",
    "on_demand_remaining_pct",
    "sand_period_end",
)
WORKER_NICK_RE = re.compile(r"^w-([a-z0-9]+)-(\d+)_?$", re.I)

HELP_TEXT = (
    "GET https://irc.ntsa.uk/bob/v1/report   fleet JSON digest\n"
    "!recycle <id>       Jeeves only: fleet recycle\n"
    "write: POST reportUrl (no !report; no !bobiverse)"
)

_SECRET_MARKERS = (
    "password=",
    "xai_api_key=",
    "connect.password",
    "x-bob-secret",
    "bob_report_secret",
    "report.secret",
    "psk=",
    "pin=",
)

_DISCONNECT_DEDUPE: dict[tuple[str, str], float] = {}

CC_SHOP = "shop"
CC_QUERY = "query"
WORKING_ON_PREFIX = "This is what I'm working on: "
WORKING_ON_SHOP_SEP = ": " + WORKING_ON_PREFIX


def looks_like_secret(text: str) -> bool:
    lower = (text or "").lower()
    return any(m in lower for m in _SECRET_MARKERS)


def secret_marker_hit(text: str) -> str | None:
    """Return the first marker *name* found in text (never a secret value)."""
    lower = (text or "").lower()
    for m in _SECRET_MARKERS:
        if m in lower:
            return m
    return None


_GIT_ACTION_WORDS = frozenset(
    {
        "opened",
        "closed",
        "reopened",
        "labeled",
        "unlabeled",
        "edited",
        "synchronize",
        "ready_for_review",
        "converted_to_draft",
        "created",
        "deleted",
        "assigned",
        "unassigned",
    }
)


def redact_git_announce_line(line: str, marker: str | None = None) -> str:
    """Replace title-bearing announce text when the announce line itself trips a marker.

    Keeps repo/action/number/author; substitutes a fixed redaction token that does not
    contain any _SECRET_MARKERS substring (do not echo the marker name if it is a marker).
    """
    # Never put marker text like "password=" into the redaction token.
    redacted = "[title redacted: secret marker]"
    raw = (line or "").strip()
    if not raw.startswith(GIT_ANNOUNCE_PREFIX):
        return GIT_ANNOUNCE_PREFIX + redacted
    rest = raw[len(GIT_ANNOUNCE_PREFIX) :].strip()
    parts = rest.split()
    if not parts:
        return GIT_ANNOUNCE_PREFIX + redacted
    event = parts[0]
    repo = parts[1] if len(parts) > 1 else ""
    actor = ""
    if " by " in rest:
        actor = rest.rsplit(" by ", 1)[-1].strip()
    # Keep action + #N when present (issues/PR); stop before title words.
    mid: list[str] = []
    for p in parts[2:]:
        if p == "by":
            break
        if p in _GIT_ACTION_WORDS or p.startswith("#"):
            mid.append(p)
            continue
        break
    bits = [event]
    if repo:
        bits.append(repo)
    bits.extend(mid)
    bits.append(redacted)
    if actor:
        bits.append(f"by {actor}")
    out = GIT_ANNOUNCE_PREFIX + " ".join(bits)
    if len(out) > MAX_GIT_ANNOUNCE:
        out = out[: MAX_GIT_ANNOUNCE - 1] + "…"
    return out


def reset_dedupe() -> None:
    _DISCONNECT_DEDUPE.clear()


def normalize_machine_id(raw: str) -> str | None:
    mid = str(raw or "").strip().lower().lstrip("#")
    if not mid or mid == "nope":
        return None
    mid = ID_ALIASES.get(mid, mid)
    if not bobstat.ID_RE.match(mid):
        return None
    return mid


def machine_from_nick(nick: str) -> str | None:
    n = (nick or "").strip().lower()
    if n in NICK_TO_MACHINE:
        return NICK_TO_MACHINE[n]
    if n.startswith("bob-"):
        return normalize_machine_id(n[4:])
    return None


_SEAT_ROSTER_CACHE: dict = {"key": None, "ids": ()}


def seat_machine_ids() -> tuple[str, ...]:
    """Machine ids a real seat nick ``<machine>-<pid>`` may carry (#39 gap 1).

    Bootstrap fleet ids PLUS the ChanServ registry (registered-machines.json) of the
    digest home, so ``win-mpre8vi4u6u-8412`` is a seat even though that machine is not in
    the 4-entry bootstrap table. Longest id first so ``ce-priority-dev1-1`` never parses
    as machine ``ce``. Cached on the registry file's mtime.
    """
    home = _default_digest_home()
    reg = registered_machines.registry_path(home) if home is not None else None
    try:
        stamp = (str(reg), reg.stat().st_mtime_ns) if reg is not None and reg.is_file() else (str(reg), 0)
    except OSError:
        stamp = (str(reg), 0)
    if _SEAT_ROSTER_CACHE["key"] != stamp:
        ids: set[str] = set()
        if home is not None:
            ids |= registered_machines.load_registered(home)
        _SEAT_ROSTER_CACHE["ids"] = tuple(sorted(ids, key=lambda m: (-len(m), m)))
        _SEAT_ROSTER_CACHE["key"] = stamp
    return _SEAT_ROSTER_CACHE["ids"]


def parse_seat_nick(nick: str) -> tuple[str, str] | None:
    """(machine_id, pid) for a legacy ``w-<short>-<pid>`` worker or a real
    ``<machine>-<pid>`` seat nick. None for bob-*, Jeeves, anything else."""
    w = parse_worker_nick(nick)
    if w:
        return w
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-"):
        return None
    for mid in seat_machine_ids():
        prefix = f"{mid}-"
        if n.startswith(prefix):
            rest = n[len(prefix):]
            if rest.isdigit() and int(rest) > 0:
                return mid, str(int(rest))
    return None


def parse_talk_seat_nick(nick: str) -> str | None:
    """{machine}-{agentPid} talk seat → machine id. Not bob-* / w-*."""
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-") or parse_worker_nick(n):
        return None
    for mid in seat_machine_ids():
        prefix = f"{mid}-"
        if n.startswith(prefix):
            rest = n[len(prefix) :]
            if rest.isdigit():
                return mid
    return None


def nick_for_machine(doc_machines: dict, machine_id: str) -> str:
    mid = normalize_machine_id(machine_id) or machine_id
    for nick, mid_map in NICK_TO_MACHINE.items():
        if mid_map == mid:
            return nick
    return f"bob-{mid}" if mid != "ce-priority-dev1" else "bob-dev1"


def shop_channel(machine_id: str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"#{mid}"


def chair_channels(home: Path | None = None) -> list[str]:
    """Jeeves: #bobiverse + ChanServ-registered shops only (registry or bootstrap fleet)."""
    if home is None:
        env_home = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
        home = Path(env_home) if env_home else None
        if home is None:
            chair = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
            if chair:
                # Prefer digest home sibling used by Start-Jeeves
                cand = Path(chair) / ".bobiverse"
                home = cand if cand.is_dir() else None
    shops = [shop_channel(mid) for mid in roster_machine_ids(home, fold=False)]   # still joins legacy #ionos
    return [FLEET_CHANNEL] + shops


def normalize_channel(raw: str) -> str:
    c = (raw or "").strip()
    if not c:
        return c
    if not c.startswith("#"):
        c = "#" + c
    mid = normalize_machine_id(c[1:])
    if mid:
        return f"#{mid}"
    return c


def worker_key(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return f"{mid}:{int(pid)}"


def worker_nick(machine_id: str, pid: int | str) -> str:
    mid = normalize_machine_id(machine_id)
    if not mid or mid not in SHORT_ID:
        raise ValueError("bad machine id")
    return f"w-{SHORT_ID[mid]}-{int(pid)}"


def parse_worker_nick(nick: str) -> tuple[str, str] | None:
    n = (nick or "").strip()
    m = WORKER_NICK_RE.match(n)
    if not m:
        return None
    short = m.group(1).lower()
    pid = m.group(2)
    mid = SHORT_TO_MACHINE.get(short)
    if not mid:
        return None
    return mid, pid


def worker_home(base: Path | str, machine_id: str, pid: int | str) -> Path:
    mid = normalize_machine_id(machine_id)
    if not mid:
        raise ValueError("bad machine id")
    return Path(base) / "workers" / mid / str(int(pid))


def parse_channel_list(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        c = part.strip()
        if not c:
            continue
        c = normalize_channel(c)
        if "|" in c:
            raise ValueError("channel must not contain |")
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def channels_for_nick(nick: str, requested: str) -> list[str]:
    """bob-* → fleet + shop; talk seats / w-* → own #{machine} only.

    First JOIN creates #{machine} on Ergo. CAST IRON (Simon 2026-09-25): worker
    processes - talk seats ({machine}-{pid}) and w-* - JOIN their own #{machine}
    ONLY, never #bobiverse or extras (#agentic_irc). Only bob-{machine}, Jeeves and
    humans belong in #bobiverse. Supersedes issue #108 / PR #107.
    """
    req = parse_channel_list(requested)
    worker = parse_worker_nick(nick)
    if worker:
        return [shop_channel(worker[0])]
    mid = machine_from_nick(nick)
    if mid:
        shop = shop_channel(mid)
        return [FLEET_CHANNEL, shop]
    talk_mid = parse_talk_seat_nick(nick)
    if talk_mid:
        return [shop_channel(talk_mid)]
    return req


def worker_channel_allowed(nick: str, channel: str) -> bool:
    """False when a worker/talk-seat nick is in any channel but its own #{machine}."""
    n = (nick or "").strip().rstrip("_")
    mid = None
    worker = parse_worker_nick(n)
    if worker:
        mid = worker[0]
    else:
        mid = parse_talk_seat_nick(n)
    if not mid:
        return True
    return normalize_channel(channel).lower() == shop_channel(mid).lower()


def expand_join_channels(raw: str) -> list[str]:
    """Split IRC JOIN target(s); Ergo may echo comma-joined names as one line."""
    text = str(raw or "").strip().lstrip(":")
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for part in text.split(","):
        for ch in parse_channel_list(part.strip()):
            key = ch.lower()
            if key not in seen:
                seen.add(key)
                out.append(ch)
    return out


def worker_irc_agent_args(
    fleet_home: Path | str,
    machine_id: str,
    pid: int | str,
    *,
    channel: str = FLEET_CHANNEL,
) -> dict[str, str]:
    """Git-task worker launch: nick, shop channel, per-pid home (agentic_build bridge)."""
    nick = worker_nick(machine_id, pid)
    home = worker_home(fleet_home, machine_id, pid)
    shop = channels_for_nick(nick, channel)[0]
    return {"nick": nick, "channel": shop, "home": str(home)}


def parse_report_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == REPORT_CMD


def parse_bobiverse_query(body: str) -> tuple[str, str | None] | None:
    """Detect legacy !bobiverse so callers can refuse it (#174)."""
    text = (body or "").strip()
    if not text:
        return None
    parts = text.split()
    if parts[0].lower() != bobtalk.BOBIVERSE_CMD:
        return None
    if len(parts) == 1:
        return ("full", None)
    rest = parts[1]
    if rest.lower() in ("?", "help"):
        return ("help", None)
    mid = normalize_machine_id(rest)
    return ("machine", mid or rest.lower())


def digest_url() -> str:
    return (os.environ.get(DIGEST_URL_ENV) or os.environ.get("BOB_DIGEST_URL") or "").strip() or DEFAULT_DIGEST_URL


def fetch_digest_http(url: str | None = None, timeout: float = 15.0) -> dict | None:
    """GET public digest JSON. Returns None on any failure."""
    import urllib.error
    import urllib.request

    target = (url or digest_url()).strip()
    if not target:
        return None
    try:
        req = urllib.request.Request(target, method="GET", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        doc = json.loads(raw or "{}")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def digest_path(home: Path) -> Path:
    return Path(home) / "digest.json"


def fleet_digest_home(home: Path) -> Path:
    """Digest root (digest.json, chair-outbox.txt).

    BOB_DIGEST_HOME wins so Jeeves (--home ~/.jeeves) drains
    chair-outbox.txt on the bobiverse digest home. Do not point --home there.
    """
    env = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
    if env:
        return Path(env)
    p = Path(home)
    if p.name.isdigit() and p.parent.parent.name == "workers":
        return p.parent.parent.parent
    return p


def _empty_machine(machine_id: str) -> dict:
    mid = normalize_machine_id(machine_id) or machine_id
    return {
        "id": mid,
        "nick": nick_for_machine({}, mid),
        "shop": shop_channel(mid) if normalize_machine_id(mid) else f"#{mid}",
        "online": False,
        "status": "I am offline",
        "working_on": "",
        "workers": {},
        "worker_list": [],
    }


def empty_digest() -> dict:
    return {
        "v": 1,
        "ts": "",
        "briefer": "",
        "machines": {},
        "events": [],
    }


def _coerce_worker(mid: str, pid: str, raw: object) -> dict:
    ent = raw if isinstance(raw, dict) else {}
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        pid_s = str(pid)
    nick = str(ent.get("nick") or "")
    if not nick:
        try:
            nick = worker_nick(mid, pid_s)
        except ValueError:
            nick = f"w-xx-{pid_s}"
    out = {
        "pid": pid_s,
        "key": str(ent.get("key") or worker_key(mid, pid_s) if normalize_machine_id(mid) else f"{mid}:{pid_s}"),
        "nick": nick,
        "kind": str(ent.get("kind") or ""),
        "state": str(ent.get("state") or "running"),
        "working_on": str(ent.get("working_on") or ""),
    }
    agent = str(ent.get("agent") or "").strip()
    model = str(ent.get("model") or "").strip()
    if agent:
        out["agent"] = agent
    if model:
        out["model"] = model
    return out


def _coerce_workers(mid: str, raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for pid, ent in raw.items():
        try:
            pid_s = str(int(str(pid)))
        except ValueError:
            continue
        out[pid_s] = _coerce_worker(mid, pid_s, ent)
    return out


# ---- v0.1.18: chair-maintained worker list (machines.<id>.workers on the wire) ----------------
# Stored as ``worker_list`` (list of {nick,state,work,updated}); the legacy pid-keyed ``workers``
# dict (merge op / gitclaim seat lookup) is untouched. Export publishes the list as ``workers``.
# FR #663: offer sets ``offered`` (not ``doing``); only ACK promotes to ``doing``.
WORKER_STATES = ("doing", "idle", "offered")
WORKER_WORK_MAX = 160
WORKER_LIST_MAX = 32
# Un-ACKed offers expire back to idle (digest export + worker-work path).
OFFERED_TIMEOUT_S = 120.0
_WORKER_NICK_RE = re.compile(r"^[A-Za-z_\[\]\\`^{|}][A-Za-z0-9_\-\[\]\\`^{|}]{0,31}$")
_NOT_WORKER_NICKS = frozenset(
    {"jeeves", "chanserv", "nickserv", "operserv", "hostserv", "memoserv", "botserv",
     "histserv", "global", "simon"}
)


def is_worker_nick(nick: str) -> bool:
    """True for a nick that may appear in a machine's worker list.

    Workers are seat nicks that speak ``!bored``/ACK/DONE. Ear/monitor nicks (``bob-*``,
    ``*_console``, ``console-*``), Jeeves, Simon and IRC services are never workers."""
    n = (nick or "").strip()
    if not n or not _WORKER_NICK_RE.match(n):
        return False
    low = n.lower()
    if low in _NOT_WORKER_NICKS or low.startswith("bob-") or low.startswith("console-"):
        return False
    if low.endswith("_console") or low.endswith("-console"):
        return False
    return True


def clean_worker_work(text: object) -> str:
    s = "".join(ch if (ch.isprintable() and ch not in "\r\n\t") else " " for ch in str(text or ""))
    s = " ".join(s.split())
    return s[:WORKER_WORK_MAX]


def _parse_worker_updated_ts(raw: object) -> float | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        from datetime import datetime

        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _coerce_worker_list(raw: object, *, now: float | None = None) -> list[dict]:
    """Normalize worker_list; FR #663 expires stale ``offered`` rows to idle."""
    import time as _time

    if not isinstance(raw, list):
        return []
    now_f = _time.time() if now is None else float(now)
    out: list[dict] = []
    seen: set[str] = set()
    for ent in raw:
        if not isinstance(ent, dict):
            continue
        nick = str(ent.get("nick") or "").strip()
        if not is_worker_nick(nick) or nick.lower() in seen:
            continue
        seen.add(nick.lower())
        state = str(ent.get("state") or "idle").strip().lower()
        if state not in WORKER_STATES:
            state = "idle"
        updated = str(ent.get("updated") or "")
        if state == "offered":
            ts = _parse_worker_updated_ts(updated)
            if ts is not None and (now_f - ts) >= float(OFFERED_TIMEOUT_S):
                state = "idle"
        # Keep work text for doing and offered (tray shows offered:<work>).
        work = clean_worker_work(ent.get("work")) if state in ("doing", "offered") else ""
        out.append(
            {"nick": nick, "state": state, "work": work, "updated": updated}
        )
    return out[:WORKER_LIST_MAX]


def _refresh_machine_activity_from_worker_list(ent: dict) -> None:
    """FR #663: machines.<id>.working_on / jobs follow worker_list; clear when none doing."""
    rows = _coerce_worker_list(ent.get("worker_list"))
    best = ""
    best_ts = ""
    for r in rows:
        if str(r.get("state") or "") != "doing":
            continue
        work = clean_worker_work(r.get("work"))
        if not work:
            continue
        upd = str(r.get("updated") or "")
        if not best or upd >= best_ts:
            best = work
            best_ts = upd
    ent["working_on"] = best
    if not best:
        # Drop stale machine-level jobs when every seat is idle/offered.
        jobs = ent.get("jobs")
        if isinstance(jobs, list) and jobs:
            ent["jobs"] = []


def _mirror_worker_list_to_legacy_workers(ent: dict, mid: str, nick: str) -> None:
    """Keep pid-keyed ``workers`` in sync with chair ``worker_list`` for one nick.

    Merge heartbeats and older monitors still read ``workers``; without this mirror,
    a seat can show ``doing`` on the tray export while the pid row stays idle (or
    the reverse after a peer merge clears ``working_on``).
    """
    n = str(nick or "").strip()
    if not n:
        return
    parsed = parse_seat_nick(n)
    if not parsed:
        return
    seat_mid, pid_s = parsed
    if normalize_machine_id(seat_mid) != normalize_machine_id(mid):
        return
    rows = _coerce_worker_list(ent.get("worker_list"))
    row = next((r for r in rows if str(r.get("nick") or "").lower() == n.lower()), None)
    workers = ent.setdefault("workers", {})
    if not isinstance(workers, dict):
        workers = {}
        ent["workers"] = workers
    prev = workers.get(pid_s) if isinstance(workers.get(pid_s), dict) else {}
    if row is None:
        if pid_s in workers:
            workers.pop(pid_s, None)
        return
    state = str(row.get("state") or "idle").strip().lower()
    work = clean_worker_work(row.get("work"))
    idle = state == "idle"
    # Legacy pid rows historically used ``running`` for active; keep ``idle`` as idle.
    legacy_state = "idle" if idle else ("running" if state in ("doing", "offered") else state)
    workers[pid_s] = _coerce_worker(
        mid,
        pid_s,
        {
            **prev,
            "state": legacy_state,
            "working_on": "" if idle else work,
            "nick": n,
            "key": worker_key(mid, pid_s),
        },
    )


def worker_list_for_export(ent: dict) -> list[dict]:
    rows = _coerce_worker_list(ent.get("worker_list"))
    return sorted(rows, key=lambda r: r["nick"].lower())


def _coerce_machine(mid: str, raw: object) -> dict:
    base = _empty_machine(mid)
    if not isinstance(raw, dict):
        return base
    online = bool(raw.get("online", False))
    status = str(raw.get("status") or ("I am online" if online else "I am offline"))
    base.update(
        {
            "nick": str(raw.get("nick") or base["nick"]),
            "shop": str(raw.get("shop") or base["shop"]),
            "online": online,
            "status": status,
            "working_on": str(raw.get("working_on") or ""),
            "workers": _coerce_workers(mid, raw.get("workers")),
            "worker_list": _coerce_worker_list(raw.get("worker_list")),
        }
    )
    if isinstance(raw.get("pcent"), dict):
        base["pcent"] = raw["pcent"]
    if isinstance(raw.get("cursor_pools"), list):
        # #114: stamp registered identity onto each pool row from the parent machine.
        base["cursor_pools"] = _coerce_cursor_pools(raw["cursor_pools"], machine_id=mid)
    if raw.get("uptime_since"):
        base["uptime_since"] = str(raw["uptime_since"])
    for key in _MERGE_PEER_FIELDS:
        if key in raw and raw[key] is not None:
            base[key] = raw[key]
    if "running" in base:
        try:
            base["running"] = int(base["running"])
        except (TypeError, ValueError):
            base["running"] = 0
    if "queued" in base:
        try:
            base["queued"] = int(base["queued"])
        except (TypeError, ValueError):
            base["queued"] = 0
    return base


def _ensure_seats(doc: dict, home: Path | None = None) -> dict:
    machines = doc.setdefault("machines", {})
    if not isinstance(machines, dict):
        machines = {}
        doc["machines"] = machines
    roster = set(roster_machine_ids(home))
    # #79: fold legacy alias keys (ionos -> win-mpre8vi4u6u) into the canonical machine. The canonical entry
    # always wins; an alias entry is only promoted when there is no canonical one yet.
    for mid in list(machines.keys()):
        if is_alias_machine_id(mid):
            ent = machines.pop(mid, None)
            canon = fold_machine_id(mid)
            if canon not in machines and isinstance(ent, dict):
                ent = dict(ent)
                ent["id"] = canon
                machines[canon] = ent
    # Drop machines not on ChanServ roster (immediate)
    for mid in list(machines.keys()):
        norm = normalize_machine_id(str(mid)) or str(mid).strip().lower()
        if norm not in roster:
            machines.pop(mid, None)
    for mid in roster:
        machines[mid] = _coerce_machine(mid, machines.get(mid))
    doc.setdefault("v", 1)
    doc.setdefault("events", [])
    if not isinstance(doc["events"], list):
        doc["events"] = []
    pools = doc.get("cursor_pools")
    if pools is not None and not isinstance(pools, list):
        doc["cursor_pools"] = []
    return doc


def load_digest(home: Path) -> dict:
    path = digest_path(home)
    if not path.exists():
        return empty_digest()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_digest()
    if not isinstance(doc, dict):
        return empty_digest()
    return _ensure_seats(doc, home)


def save_digest(home: Path, doc: dict) -> None:
    """Atomically write digest.json with unique-temp and Windows retry handling.

    The fresh-temp retry also covers AV/racing cleanup removing the temporary file
    between write and replace (FR #36), while write/replace helpers cover WinError
    5/32 sharing violations (FR #35/#37). FR #951: after replace retries exhaust,
    fall back to ``shutil.copyfile`` so open readers without FILE_SHARE_DELETE
    do not fail the webhook report route.
    """
    path = digest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_digest_tmp(path)
    payload = json.dumps(doc, indent=2) + "\n"
    last_missing: FileNotFoundError | None = None
    for _attempt in range(2):
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:12]}.tmp")
        try:
            _write_text_with_retry(tmp, payload)
            _replace_with_retry(tmp, path)
            return
        except FileNotFoundError as exc:
            last_missing = exc
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
    assert last_missing is not None
    raise last_missing


_REPLACE_RETRY_DELAYS = (0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.0, 1.0)
_STALE_TMP_AGE_S = 120.0


def _is_sharing_error(exc: OSError) -> bool:
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "winerror", None) in (5, 32)


def _write_text_with_retry(path: Path, text: str) -> None:
    """Write ``path`` retrying Windows sharing / access-denied (intake #37)."""
    last: OSError | None = None
    for delay in (0.0,) + _REPLACE_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            path.write_text(text, encoding="utf-8")
            return
        except OSError as exc:
            if not _is_sharing_error(exc):
                raise
            last = exc
    assert last is not None
    raise last


def _replace_with_retry(src: Path, dst: Path) -> None:
    last: OSError | None = None
    for delay in (0.0,) + _REPLACE_RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            os.replace(src, dst)
            return
        except OSError as exc:
            if not _is_sharing_error(exc):
                raise
            last = exc
    # FR #951: sustained Access denied on replace (open handle without DELETE share).
    # Overwriting bytes via copyfile often succeeds when replace cannot unlink dst.
    try:
        shutil.copyfile(src, dst)
        return
    except OSError as exc:
        if last is not None:
            raise last from exc
        raise


def _cleanup_stale_digest_tmp(path: Path, max_age_s: float | None = None) -> int:
    """Remove orphaned ``digest.json*.tmp`` left by crashed writers. Returns count removed."""
    age = _STALE_TMP_AGE_S if max_age_s is None else max_age_s
    removed = 0
    now = time.time()
    try:
        cands = list(path.parent.glob(path.name + "*.tmp"))
    except OSError:
        return 0
    for p in cands:
        try:
            if now - p.stat().st_mtime >= age:
                p.unlink()
                removed += 1
        except OSError:
            continue
    return removed


_DIGEST_THREAD_LOCK = threading.RLock()
_LOCK_STATE = threading.local()

DIGEST_LOCK_STALE_ENV = "BOB_DIGEST_LOCK_STALE_S"
DEFAULT_DIGEST_LOCK_STALE_S = 30.0
DEFAULT_DIGEST_LOCK_TIMEOUT_S = 2.0
# FR #1388: live foreign holder (e.g. chair irc_agent) longer than this → breakable.
# Shorter than full stale so BobCallback HTTP / startup is not wedged for 30s.
DIGEST_LOCK_FOREIGN_ENV = "BOB_DIGEST_LOCK_FOREIGN_S"
DEFAULT_DIGEST_LOCK_FOREIGN_S = 12.0


class DigestLockBusy(Exception):
    """digest.lock could not be acquired after break-and-retry (FR #1136). Map to HTTP 503."""


def digest_lock_path(home: Path) -> Path:
    return digest_path(home).with_name("digest.lock")


def digest_lock_stale_s() -> float:
    try:
        return max(1.0, float(os.environ.get(DIGEST_LOCK_STALE_ENV) or DEFAULT_DIGEST_LOCK_STALE_S))
    except ValueError:
        return DEFAULT_DIGEST_LOCK_STALE_S


def digest_lock_foreign_s() -> float:
    """Max age for a live *other* process's digest.lock before BobCallback may break it (FR #1388)."""
    try:
        return max(1.0, float(os.environ.get(DIGEST_LOCK_FOREIGN_ENV) or DEFAULT_DIGEST_LOCK_FOREIGN_S))
    except ValueError:
        return DEFAULT_DIGEST_LOCK_FOREIGN_S


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            # SYNCHRONIZE — OpenProcess succeeds for live PIDs we can see; ACCESS_DENIED (5) often
            # means the process exists but we lack rights.
            h = ctypes.windll.kernel32.OpenProcess(0x00100000, 0, int(pid))
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return int(ctypes.windll.kernel32.GetLastError()) == 5
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_lock_meta(lock_path: Path) -> tuple[int | None, float | None, float]:
    """Return (pid, stamped_ts, mtime_age_s). Missing file → (None, None, 0)."""
    try:
        st = lock_path.stat()
    except OSError:
        return None, None, 0.0
    age = max(0.0, time.time() - float(st.st_mtime))
    pid = None
    stamped = None
    try:
        raw = lock_path.read_bytes()
    except OSError:
        return None, None, age
    if not raw:
        return None, None, age
    try:
        text = raw.decode("utf-8", errors="replace").strip()
    except Exception:
        return None, None, age
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and lines[0].isdigit():
        pid = int(lines[0])
    if len(lines) >= 2:
        with contextlib.suppress(ValueError):
            stamped = float(lines[1])
    return pid, stamped, age


def break_stale_digest_lock(home: Path, max_age_s: float | None = None) -> dict | None:
    """Unlink ``digest.lock`` when empty, older than ``max_age_s``, holder PID is dead (FR #1136),
    or a *foreign* live holder exceeds ``digest_lock_foreign_s`` (FR #1388).

    Never breaks a fresh lock held by *this* PID. Returns a small info dict when broken, else None.
    Logs ``lock-broken age=... pid=...``.
    """
    lock_path = digest_lock_path(Path(home))
    if not lock_path.exists():
        return None
    max_age = digest_lock_stale_s() if max_age_s is None else float(max_age_s)
    foreign_age = digest_lock_foreign_s()
    pid, stamped, age = _read_lock_meta(lock_path)
    size = 0
    with contextlib.suppress(OSError):
        size = lock_path.stat().st_size
    reason = None
    me = os.getpid()
    own_live = pid is not None and int(pid) == int(me) and _pid_alive(pid)
    if size == 0:
        reason = "empty"
    elif age >= max_age:
        # Never unlink a lock still held by *this* live process — health-watchdog
        # GET timeouts used to break our own 30s+ holder (mtime not refreshed) and
        # cascade ConnectionAbortedError + foreign-stale fights with the chair.
        if own_live:
            reason = None
        else:
            reason = "stale"
    elif pid is not None and not _pid_alive(pid):
        reason = "dead-pid"
    elif (
        pid is not None
        and int(pid) != int(me)
        and _pid_alive(pid)
        and age >= foreign_age
    ):
        # Chair irc_agent (or other) held digest.lock while BobCallback needed :7700.
        reason = "foreign-stale"
    if reason is None:
        return None
    with contextlib.suppress(OSError):
        lock_path.unlink()
    info = {"age": round(age, 3), "pid": pid, "reason": reason, "stamped": stamped}
    print(f"lock-broken age={info['age']} pid={pid} reason={reason}", flush=True)
    return info


def digest_lock_age_s(home: Path) -> float | None:
    """Age in seconds of ``digest.lock`` mtime, or None if absent."""
    lock_path = digest_lock_path(Path(home))
    try:
        return max(0.0, time.time() - lock_path.stat().st_mtime)
    except OSError:
        return None


def digest_lock_holder_pid(home: Path) -> int | None:
    """PID stamped in ``digest.lock``, or None if absent/unreadable (FR #1388)."""
    pid, _stamped, _age = _read_lock_meta(digest_lock_path(Path(home)))
    return pid


def last_digest_write_iso(home: Path) -> str:
    path = digest_path(Path(home))
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.fromtimestamp(ts, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _try_advisory_lock(fh, timeout_s: float) -> bool:
    deadline = time.monotonic() + max(0.05, float(timeout_s))
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)


def _write_lock_holder(fh) -> None:
    payload = f"{os.getpid()}\n{time.time():.3f}\n".encode("utf-8")
    with contextlib.suppress(OSError):
        fh.seek(0)
        fh.truncate(0)
        fh.write(payload)
        fh.flush()


def _unlock_advisory(fh) -> None:
    with contextlib.suppress(OSError):
        if os.name == "nt":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def digest_lock(
    home: Path,
    timeout_s: float | None = None,
    *,
    raise_busy: bool = True,
):
    """Serialise digest read-modify-write across threads AND processes (#51 / FR #1136).

    Re-entrant per thread. Cross-process part is an advisory lock on ``digest.lock``.
    Before waiting: break empty/stale/dead-PID locks. Bounded wait, then break-and-retry once;
    still busy → ``DigestLockBusy`` (HTTP 503) when ``raise_busy`` else proceed unlocked.
    """
    depth = getattr(_LOCK_STATE, "depth", 0)
    if depth > 0:
        _LOCK_STATE.depth = depth + 1
        try:
            yield
        finally:
            _LOCK_STATE.depth -= 1
        return

    wait_s = DEFAULT_DIGEST_LOCK_TIMEOUT_S if timeout_s is None else float(timeout_s)
    root = Path(home)
    break_stale_digest_lock(root)

    fh = None
    locked = False
    _DIGEST_THREAD_LOCK.acquire()
    try:
        try:
            lock_path = digest_lock_path(root)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fh = open(lock_path, "a+b")
            locked = _try_advisory_lock(fh, wait_s)
            if not locked:
                # Release thread lock while we break+retry so other requests are not serialized
                # behind a full wait (the historic hang mode).
                _DIGEST_THREAD_LOCK.release()
                try:
                    with contextlib.suppress(OSError):
                        fh.close()
                    fh = None
                    break_stale_digest_lock(root)
                    time.sleep(0.05)
                finally:
                    _DIGEST_THREAD_LOCK.acquire()
                lock_path = digest_lock_path(root)
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                fh = open(lock_path, "a+b")
                locked = _try_advisory_lock(fh, wait_s)
            if locked:
                _write_lock_holder(fh)
            elif raise_busy:
                with contextlib.suppress(OSError):
                    if fh is not None:
                        fh.close()
                fh = None
                raise DigestLockBusy("digest.lock busy after break-and-retry")
        except DigestLockBusy:
            raise
        except OSError:
            with contextlib.suppress(OSError):
                if fh is not None:
                    fh.close()
            fh = None
            if raise_busy:
                raise DigestLockBusy("digest.lock open/lock failed") from None
        _LOCK_STATE.depth = 1
        # Refresh holder stamp so long holds do not look "stale" to the watchdog.
        if locked and fh is not None:
            with contextlib.suppress(OSError):
                _write_lock_holder(fh)
        # FR #2902: heartbeat every 10s while held so mtime/age stay fresh across
        # long critical sections (still prefer not to do slow I/O under the lock).
        stop_hb = threading.Event()
        hb_fh = fh if locked else None

        def _heartbeat() -> None:
            while not stop_hb.wait(10.0):
                if hb_fh is None:
                    return
                with contextlib.suppress(OSError):
                    _write_lock_holder(hb_fh)

        hb_thread = None
        if hb_fh is not None:
            hb_thread = threading.Thread(
                target=_heartbeat, name="digest-lock-heartbeat", daemon=True
            )
            hb_thread.start()
        try:
            yield
        finally:
            stop_hb.set()
            _LOCK_STATE.depth = 0
            if fh is not None:
                if locked:
                    _unlock_advisory(fh)
                with contextlib.suppress(OSError):
                    fh.close()
    finally:
        with contextlib.suppress(RuntimeError):
            _DIGEST_THREAD_LOCK.release()

def _digest_locked(fn):
    """Decorator: run a ``fn(home, ...)`` digest mutator under :func:`digest_lock`."""

    @functools.wraps(fn)
    def wrapper(home, *args, **kwargs):
        with digest_lock(Path(home)):
            return fn(home, *args, **kwargs)

    return wrapper


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _note_event(doc: dict, kind: str, **fields: object) -> None:
    ev = {"ts": _utc_now_iso(), "kind": kind}
    ev.update(fields)
    events = doc.setdefault("events", [])
    if not isinstance(events, list):
        events = []
    events.append(ev)
    doc["events"] = events[-20:]


def _roll_working_on(ent: dict) -> None:
    """Refresh machines.<id>.working_on from legacy pid workers, else worker_list.

    Peer merge heartbeats often touch the pid-keyed ``workers`` dict with empty
    ``working_on``. Blanking machine activity in that case wiped the chair
    ``worker_list`` feed (ACK/DONE via worker-work), so the public digest looked
    idle while seats were still doing.
    """
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    for w in workers.values():
        text = str((w or {}).get("working_on") or "").strip()
        if text:
            ent["working_on"] = text
            return
    # Fall back to chair-maintained worker_list (FR #663); do not blank activity.
    _refresh_machine_activity_from_worker_list(ent)


def _machine_entry(doc: dict, machine_id: str) -> dict:
    mid = normalize_machine_id(machine_id) or machine_id
    machines = doc.setdefault("machines", {})
    ent = _coerce_machine(mid, machines.get(mid))
    machines[mid] = ent
    return ent


def _set_online(ent: dict, online: bool) -> None:
    ent["online"] = online
    ent["status"] = "I am online" if online else "I am offline"
    if not online:
        ent["working_on"] = ""
        ent["workers"] = {}
        ent["worker_list"] = []


@dataclass
class ReportOutcome:
    ok: bool
    err: str | None = None
    help_text: str | None = None
    speak_channel: str | None = None
    echo_raw: bool = False


@dataclass
class PresenceOutcome:
    ok: bool
    err: str | None = None
    actions: list[str] = field(default_factory=list)
    shop_closed: bool = False
    deleted_pid: str | None = None
    machine_id: str | None = None


@dataclass
class CallbackOutcome:
    ok: bool
    err: str = ""
    actions: list[str] = field(default_factory=list)
    changed: bool = True
    body: bytes | None = None


@dataclass
class GitWebhookOutcome:
    ok: bool
    err: str = ""
    announced: bool = False


GIT_ANNOUNCE_PREFIX = "GIT "
MAX_GIT_ANNOUNCE = 380


CHAIR_NICK_ENV = "BOB_CHAIR_NICK"


def digest_chair_nick(home: Path) -> str | None:
    """Dedicated digest chair (issue #73). Env wins over digest.json chairNick."""
    env = (os.environ.get(CHAIR_NICK_ENV) or "").strip()
    if env:
        return env
    doc = load_digest(home)
    raw = str(doc.get("chairNick") or doc.get("chair_nick") or "").strip()
    return raw or None


def chair_mode_active(home: Path) -> bool:
    return bool(digest_chair_nick(home))


@_digest_locked
def persist_chair_nick(home: Path, nick: str) -> None:
    """Write digest chair identity to shared digest.json (issue #73 / #78)."""
    n = (nick or "").strip()
    if not n:
        return
    root = fleet_digest_home(Path(home))
    doc = load_digest(root)
    if str(doc.get("chairNick") or "") == n:
        return
    doc["chairNick"] = n
    save_digest(root, doc)


def _fleet_spam_privmsg_body(body: str) -> bool:
    """Outbox / channel lines that must not hit #bobiverse when chair mode is on."""
    raw = (body or "").strip()
    if not raw:
        return False
    low = raw.lower().replace("\x01", " ")
    if low.startswith("bob digest v1"):
        return True
    if low.startswith("bob tray v1"):
        return True
    if "i am offline" in low or "i am online" in low:
        return True
    if "working on" in low:
        return True
    if " is on " in low and (" now." in low or " now" in low):
        return True
    if low.startswith("action ") or " action " in low:
        return True
    if " here. weekly=" in low:
        return True
    return False


def outbox_line_spam_for_fleet_channel(line: str, *, default_channel: str = FLEET_CHANNEL) -> bool:
    """True if line must be dropped (not sent) to #bobiverse under chair mode."""
    text = (line or "").strip()
    if not text:
        return False
    to_fleet = default_channel.lower() == FLEET_CHANNEL.lower()
    body = text
    if text.upper().startswith("PRIVMSG "):
        rest = text[8:]
        target, _, tail = rest.partition(" ")
        to_fleet = target.lstrip(":").lower() == FLEET_CHANNEL.lower()
        body = tail[1:] if tail.startswith(":") else (text.split(" :", 1)[1] if " :" in text else text)
    if not to_fleet:
        return False
    return _fleet_spam_privmsg_body(body)


def _machine_fingerprint(ent: dict) -> str:
    view = {
        "online": ent.get("online"),
        "status": ent.get("status"),
        "working_on": ent.get("working_on"),
        "pcent": ent.get("pcent"),
        "cursor_pools": ent.get("cursor_pools"),
        "uptime_since": ent.get("uptime_since"),
        "workers": ent.get("workers"),
        "worker_list": ent.get("worker_list"),
    }
    for key in _MERGE_PEER_FIELDS:
        if key in ent:
            view[key] = ent.get(key)
    return json.dumps(view, sort_keys=True, separators=(",", ":"))


def _merge_worker_on_ent(
    ent: dict, mid: str, pid_s: str, working_on: str, kind: str = "grok"
) -> list[str]:
    text = (working_on or "").strip()
    if not text:
        return []
    if looks_like_secret(text) or looks_like_secret(kind):
        return []
    workers = ent.setdefault("workers", {})
    prev = workers.get(pid_s) or {}
    prev_wo = str(prev.get("working_on") or "").strip()
    if prev_wo == text and prev:
        return []
    ent["online"] = True
    ent["status"] = "I am online"
    w = _coerce_worker(
        mid,
        pid_s,
        {
            **prev,
            "kind": kind or prev.get("kind") or "grok",
            "state": prev.get("state") or "running",
            "working_on": text,
            "nick": prev.get("nick") or worker_nick(mid, pid_s),
            "key": worker_key(mid, pid_s),
        },
    )
    workers[pid_s] = w
    _roll_working_on(ent)
    return [f"'s pid {pid_s} on {mid} is working on {text}"]


_POOL_PCENT_KEY = {"grok-weekly": "grok-chat", "other-models": "other-models"}


def _store_machine_pool_rows(ent: dict, raw_rows: object) -> None:
    """#41: keep THIS machine's own pool rows in ``machines.<id>.cursor_pools``.

    A machine reports its LOCAL pools (grok-chat weekly + Cursor bars, each with its own
    period_end). They used to replace one fleet-wide list (and were dropped entirely when bob's
    row shape did not coerce). Now: replace only this machine's rows (never with an empty
    list), and backfill ``pcent`` / ``period_end`` / ``cursor_period_end`` gaps from them so the
    lesser-across-machines pool bars and the expiry masking work for rows-only reporters.
    """
    mid = str(ent.get("id") or "")
    rows = _coerce_cursor_pools(raw_rows, machine_id=mid or None)
    if not rows:
        return
    account = str(ent.get("nick") or "") or None
    channel = str(ent.get("shop") or "") or None
    stamped: list[dict] = []
    for row in rows:
        stamped.append(_stamp_pool_identity(row, mid, account=account, channel=channel))
    ent["cursor_pools"] = stamped
    pcent = ent.get("pcent") if isinstance(ent.get("pcent"), dict) else {}
    changed = False
    for row in stamped:
        pid = str(row.get("id") or "")
        rem = row.get("remaining")
        pe = row.get("period_end")
        if rem is not None and not _pcent_key_present(pcent, pid):
            pcent = dict(pcent)
            pcent[_POOL_PCENT_KEY.get(pid, pid)] = rem
            changed = True
        if pe:
            field = "period_end" if pid == "grok-weekly" else "cursor_period_end"
            if ent.get(field) in (None, ""):
                ent[field] = pe
    if changed:
        ent["pcent"] = pcent


def _apply_merge_payload(doc: dict, mid: str, payload: dict) -> list[str]:
    """Mutate digest doc for one machine merge; return new English actions."""
    actions: list[str] = []
    pid_raw = payload.get("pid")
    ent = _machine_entry(doc, mid)
    if pid_raw is not None and str(pid_raw) != "" and "working_on" in payload:
        try:
            pid_s = str(int(str(pid_raw)))
        except ValueError:
            return []
        kind = str(payload.get("kind") or "grok")
        actions.extend(_merge_worker_on_ent(ent, mid, pid_s, str(payload.get("working_on") or ""), kind=kind))
        workers = ent.setdefault("workers", {})
        current = workers.get(pid_s)
        if isinstance(current, dict):
            if str(payload.get("state") or "").strip().lower() == "idle":
                current["state"] = "idle"
                current["working_on"] = ""
                current.pop("agent", None)
                current.pop("model", None)
                _roll_working_on(ent)
            else:
                if str(payload.get("agent") or "").strip():
                    current["agent"] = str(payload.get("agent")).strip()
                if str(payload.get("model") or "").strip():
                    current["model"] = str(payload.get("model")).strip()
    if "online" in payload:
        ent["online"] = bool(payload["online"])
        ent["status"] = "I am online" if ent["online"] else "I am offline"
    if payload.get("status"):
        ent["status"] = str(payload["status"])
    # Period roll (weekly sand) → clear last period's weekly when the new window has no figure yet.
    weekly_rolled = _period_rolled(ent.get("period_end"), payload.get("period_end"))
    # t785u: the machine moved to a new weekly period but has no measured figure for it yet: last period's % must not
    # linger next to the new reset (MarchHare showed weekly=8 against a reset 7 days later).
    if weekly_rolled and payload.get("period_end") and payload.get("weekly") is None:
        ent.pop("weekly", None)
    # FR #976: reporter says weekly is unknown — clear a stuck 0 (lesser ratchet left 0 forever).
    weekly_known = payload.get("weekly_known")
    if weekly_known is False or (
        "weekly_known" in payload and weekly_known in (0, "false", "False", "0", "")
    ):
        ent.pop("weekly", None)
    if "pcent" in payload and isinstance(payload["pcent"], dict):
        # FR #976: per-machine pcent is replace-latest (reporter's current reading), not min-ratchet.
        ent["pcent"] = _merge_pcent_lesser(
            ent.get("pcent"), payload["pcent"], replace=True
        )
    if payload.get("uptime_since"):
        ent["uptime_since"] = str(payload["uptime_since"])
    if isinstance(payload.get("cursor_pools"), list):
        _store_machine_pool_rows(ent, payload["cursor_pools"])
    if pid_raw is not None and str(pid_raw) != "":
        try:
            pid_s = str(int(str(pid_raw)))
        except ValueError:
            return actions
        if "working_on" not in payload:
            wo = str(payload.get("working_on") or "")
            if looks_like_secret(wo):
                return actions
            workers = ent.setdefault("workers", {})
            prev = workers.get(pid_s) or {}
            state = str(payload.get("state", prev.get("state") or "running") or "running")
            idle = state.strip().lower() == "idle"
            merged = {
                **prev,
                "kind": payload.get("kind", prev.get("kind") or ""),
                "state": "idle" if idle else state,
                "working_on": "" if idle else (prev.get("working_on") or ""),
                "nick": payload.get("nick") or prev.get("nick") or worker_nick(mid, pid_s),
            }
            if idle:
                merged["agent"] = ""
                merged["model"] = ""
            else:
                if str(payload.get("agent") or "").strip():
                    merged["agent"] = str(payload.get("agent")).strip()
                if str(payload.get("model") or "").strip():
                    merged["model"] = str(payload.get("model")).strip()
            workers[pid_s] = _coerce_worker(mid, pid_s, merged)
            _roll_working_on(ent)
    elif "working_on" in payload and (pid_raw is None or str(pid_raw) == ""):
        # Empty machine-level heartbeat must not wipe chair worker-work activity.
        # Peers often POST merge with working_on="" (no pid); blanking here made TipForm
        # / public digest look idle while worker_list still had doing seats.
        text = str(payload.get("working_on") or "").strip()
        if text:
            ent["working_on"] = text
        else:
            _roll_working_on(ent)
    for key in _MERGE_PEER_FIELDS:
        if key not in payload or payload[key] is None:
            continue
        val = payload[key]
        if key == "jobs" and not isinstance(val, list):
            continue
        if key == "pcent" and isinstance(val, dict):
            continue
        if key in ("weekly",) and val is not None:
            # FR #976: skip write when reporter marked weekly unknown (cleared above).
            if weekly_known is False or (
                "weekly_known" in payload and weekly_known in (0, "false", "False", "0", "")
            ):
                continue
            # Per-machine weekly is replace-latest (not min-ratchet).
            ent[key] = val
            continue
        ent[key] = val
    if "running" in ent:
        try:
            ent["running"] = int(ent["running"])
        except (TypeError, ValueError):
            ent["running"] = 0
    if "queued" in ent:
        try:
            ent["queued"] = int(ent["queued"])
        except (TypeError, ValueError):
            ent["queued"] = 0
    return actions


def apply_report(home: Path, sender_nick: str, briefer_nick: str, body: str) -> ReportOutcome:
    """Scrubbed: never ingest !report. Secret-shaped lines are dropped."""
    del home, sender_nick, briefer_nick
    if looks_like_secret(body):
        return ReportOutcome(ok=False, err="ERR report refused (secret-like token)")
    return ReportOutcome(ok=False, err=REPORT_GONE)


@_digest_locked
def clear_seat_doing(
    home: Path,
    nick: str,
    *,
    briefer_nick: str = "",
    only_if_work_contains: str = "",
) -> PresenceOutcome:
    """Set a seat idle in digest ``worker_list`` + ``workers`` (FR #1430).

    Used when an accepted MERGED MRB is purged from the queue while the seat's
    digest still shows ``doing bobiverse MRB #N`` — that false busy made every
    !bored return ``nak busy`` and stranded the next offer (e.g. repo UAT).
    When ``only_if_work_contains`` is set, clear only if current work/working_on
    mentions that needle (PR number / task id).
    """
    parsed = parse_seat_nick(nick)
    if not parsed:
        return PresenceOutcome(ok=False, err="bad nick")
    mid, pid = parsed
    pid_s = str(pid)
    needle = str(only_if_work_contains or "").strip().lstrip("#").lower()
    doc = load_digest(home)
    ent = _machine_entry(doc, mid)
    changed = False
    rows = list(ent.get("worker_list") or [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("nick") or "").strip().lower() != str(nick).strip().lower():
            # also match short w-io-* forms via pid suffix
            if not str(row.get("nick") or "").endswith(f"-{pid_s}"):
                continue
        work = str(row.get("work") or "")
        if needle and needle not in work.lower() and f"#{needle}" not in work.lower():
            continue
        if str(row.get("state") or "") != "idle" or work:
            row["state"] = "idle"
            row["work"] = ""
            row["updated"] = _utc_now_iso()
            changed = True
    workers = ent.setdefault("workers", {})
    w = workers.get(pid_s) if isinstance(workers.get(pid_s), dict) else None
    if isinstance(w, dict):
        wo = str(w.get("working_on") or "")
        if (not needle) or (needle in wo.lower()) or (f"#{needle}" in wo.lower()):
            if str(w.get("state") or "") != "idle" or wo:
                w["state"] = "idle"
                w["working_on"] = ""
                changed = True
    if not changed:
        return PresenceOutcome(ok=True, machine_id=mid)
    ent["worker_list"] = _coerce_worker_list(rows)
    _refresh_machine_activity_from_worker_list(ent)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    _note_event(doc, "worker-idle-purge", machine=mid, nick=nick, pid=pid_s)
    save_digest(home, doc)
    return PresenceOutcome(ok=True, machine_id=mid)


@_digest_locked
def merge_worker_working_on(
    home: Path,
    machine_id: str,
    pid: int | str,
    working_on: str,
    briefer_nick: str = "",
    kind: str = "grok",
) -> PresenceOutcome:
    text = (working_on or "").strip()
    if not text:
        return PresenceOutcome(ok=False, err="working_on required")
    if looks_like_secret(text) or looks_like_secret(kind):
        return PresenceOutcome(ok=False, err="secret")
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        return PresenceOutcome(ok=False, err="bad pid")
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    workers = ent.setdefault("workers", {})
    prev = workers.get(pid_s) or {}
    prev_wo = str(prev.get("working_on") or "").strip()
    if prev_wo == text and prev:
        return PresenceOutcome(ok=True, machine_id=mid)
    ent["online"] = True
    ent["status"] = "I am online"
    w = _coerce_worker(
        mid,
        pid_s,
        {
            **prev,
            "kind": kind or prev.get("kind") or "grok",
            "state": prev.get("state") or "running",
            "working_on": text,
            "nick": prev.get("nick") or worker_nick(mid, pid_s),
            "key": worker_key(mid, pid_s),
        },
    )
    workers[pid_s] = w
    _roll_working_on(ent)
    _note_event(doc, "worker-start" if not prev else "working_on", machine=mid, pid=pid_s, working_on=text)
    save_digest(home, doc)
    action = f"'s pid {pid_s} on {mid} is working on {text}"
    return PresenceOutcome(ok=True, actions=[action], machine_id=mid)


def start_worker(
    home: Path,
    machine_id: str,
    pid: int | str,
    working_on: str,
    kind: str = "grok",
    briefer_nick: str = "",
) -> PresenceOutcome:
    return merge_worker_working_on(home, machine_id, pid, working_on, briefer_nick, kind=kind)


@_digest_locked
def delete_worker(home: Path, machine_id: str, pid: int | str, briefer_nick: str = "", now: float | None = None) -> PresenceOutcome:
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    try:
        pid_s = str(int(str(pid)))
    except ValueError:
        return PresenceOutcome(ok=False, err="bad pid")
    import time

    ts = time.time() if now is None else now
    key = (mid, pid_s)
    last = _DISCONNECT_DEDUPE.get(key, 0.0)
    if ts - last < DISCONNECT_DEDUPE_S:
        return PresenceOutcome(ok=True, deleted_pid=pid_s, machine_id=mid)
    _DISCONNECT_DEDUPE[key] = ts
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    workers = ent.setdefault("workers", {})
    gone = workers.pop(pid_s, None)
    _roll_working_on(ent)
    if gone is not None:
        _note_event(doc, "worker-delete", machine=mid, pid=pid_s)
        save_digest(home, doc)
        nick = str(gone.get("nick") or worker_nick(mid, pid_s))
        shop = ent.get("shop") or shop_channel(mid)
        action = f"sees {nick} drop from {shop} (pid {pid_s})"
        return PresenceOutcome(ok=True, actions=[action], deleted_pid=pid_s, machine_id=mid)
    save_digest(home, doc)
    return PresenceOutcome(ok=True, deleted_pid=pid_s, machine_id=mid)


def _apply_worker_op(home: Path, op: str, mid: str, payload: dict, briefer_nick: str = "") -> CallbackOutcome:
    """worker-upsert / worker-remove / worker-work (chair-side, roster machines only)."""
    nick = str(payload.get("nick") or "").strip()
    if not is_worker_nick(nick):
        return CallbackOutcome(ok=False, err="bad nick")
    state_raw = payload.get("state")
    state = str(state_raw).strip().lower() if state_raw not in (None, "") else ""
    if state and state not in WORKER_STATES:
        return CallbackOutcome(ok=False, err="bad state")
    work_raw = payload.get("work")
    if work_raw is not None and not isinstance(work_raw, str):
        return CallbackOutcome(ok=False, err="bad work")
    if looks_like_secret(str(work_raw or "")):
        return CallbackOutcome(ok=False, err="secret")
    if op == "worker-work" and not state:
        return CallbackOutcome(ok=False, err="state required")
    doc = load_digest(home)
    ent = _machine_entry(doc, mid)
    rows = list(ent.get("worker_list") or [])
    idx = next((i for i, r in enumerate(rows) if r["nick"].lower() == nick.lower()), -1)
    def _sig(rs):
        return json.dumps([{k: v for k, v in r.items() if k != "updated"} for r in rs], sort_keys=True)

    before = _sig(rows)
    now_iso = _utc_now_iso()
    touched = nick
    if op == "worker-remove":
        if idx < 0:
            return CallbackOutcome(ok=True, changed=False)
        rows.pop(idx)
        event = "worker-remove"
        after_rows = _coerce_worker_list(rows)
        ent["worker_list"] = after_rows
        _refresh_machine_activity_from_worker_list(ent)
        _mirror_worker_list_to_legacy_workers(ent, mid, nick)
        if briefer_nick:
            doc["briefer"] = briefer_nick
        doc["ts"] = now_iso
        _note_event(doc, event, machine=mid, nick=nick)
        save_digest(home, doc)
        # FR #3400: ACKed jobs held by a departed seat return to unaccepted (prior ACK void).
        try:
            import gitclaim as _gitclaim

            _gitclaim.release_accepted_for_departed_nick(home, nick)
        except Exception:
            pass
        return CallbackOutcome(ok=True, changed=True)
    else:
        if idx < 0:
            if len(rows) >= WORKER_LIST_MAX:
                return CallbackOutcome(ok=False, err="too many workers")
            row = {"nick": nick, "state": "idle", "work": "", "updated": now_iso}
            rows.append(row)
        else:
            row = rows[idx]
        if state:
            row["state"] = state
        if row["state"] in ("doing", "offered"):
            if work_raw is not None:
                row["work"] = clean_worker_work(work_raw)
            if not row["work"]:
                row["work"] = "working" if row["state"] == "doing" else "offered"
        else:
            row["work"] = ""
        event = op
    after_rows = _coerce_worker_list(rows)
    if _sig(after_rows) == before:
        # Still refresh machine activity (timeout may have expired offered -> idle).
        ent["worker_list"] = after_rows
        _refresh_machine_activity_from_worker_list(ent)
        _mirror_worker_list_to_legacy_workers(ent, mid, nick)
        save_digest(home, doc)
        return CallbackOutcome(ok=True, changed=False)
    for r in after_rows:
        if r["nick"].lower() == touched.lower():
            r["updated"] = now_iso
    ent["worker_list"] = after_rows
    _refresh_machine_activity_from_worker_list(ent)
    _mirror_worker_list_to_legacy_workers(ent, mid, nick)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = now_iso
    _note_event(doc, event, machine=mid, nick=nick)
    save_digest(home, doc)
    return CallbackOutcome(ok=True, changed=True)


@_digest_locked
def shop_down(home: Path, machine_id: str, briefer_nick: str = "") -> PresenceOutcome:
    mid = normalize_machine_id(machine_id)
    if not mid:
        return PresenceOutcome(ok=False, err="bad machine")
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    nick = str(ent.get("nick") or nick_for_machine({}, mid))
    shop = ent.get("shop") or shop_channel(mid)
    _set_online(ent, False)
    _note_event(doc, "shop-down", machine=mid)
    save_digest(home, doc)
    action = f"lost {nick} — {shop} closed"
    return PresenceOutcome(ok=True, actions=[action], shop_closed=True, machine_id=mid)


@_digest_locked
def apply_join(home: Path, nick: str, channel: str, briefer_nick: str = "") -> PresenceOutcome:
    ch = normalize_channel(channel)
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        shop = shop_channel(mid)
        if ch.lower() != shop.lower():
            return PresenceOutcome(ok=True, machine_id=mid)
        doc = load_digest(home)
        if briefer_nick:
            doc["briefer"] = briefer_nick
        doc["ts"] = _utc_now_iso()
        ent = _machine_entry(doc, mid)
        workers = ent.setdefault("workers", {})
        if pid not in workers:
            workers[pid] = _coerce_worker(mid, pid, {"state": "joined", "nick": worker_nick(mid, pid)})
            _note_event(doc, "worker-join", machine=mid, pid=pid)
            save_digest(home, doc)
        return PresenceOutcome(ok=True, machine_id=mid)
    mid = machine_from_nick(nick)
    if not mid:
        return PresenceOutcome(ok=True)
    shop = shop_channel(mid)
    if ch.lower() not in (FLEET_CHANNEL, shop.lower()):
        return PresenceOutcome(ok=True, machine_id=mid)
    doc = load_digest(home)
    if briefer_nick:
        doc["briefer"] = briefer_nick
    doc["ts"] = _utc_now_iso()
    ent = _machine_entry(doc, mid)
    ent["nick"] = (nick or "").strip() or ent["nick"]
    was_offline = not ent.get("online")
    ent["online"] = True
    ent["status"] = "I am online"
    if was_offline:
        ent["working_on"] = ""
        _note_event(doc, "machine-join", machine=mid)
    save_digest(home, doc)
    return PresenceOutcome(ok=True, machine_id=mid)


@_digest_locked
def apply_part(home: Path, nick: str, channel: str, briefer_nick: str = "") -> PresenceOutcome:
    ch = normalize_channel(channel)
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        if ch.lower() == shop_channel(mid).lower():
            return delete_worker(home, mid, pid, briefer_nick)
        return PresenceOutcome(ok=True, machine_id=mid)
    mid = machine_from_nick(nick)
    if mid and ch.lower() == shop_channel(mid).lower():
        return shop_down(home, mid, briefer_nick)
    return PresenceOutcome(ok=True, machine_id=mid)


@_digest_locked
def apply_quit(home: Path, nick: str, briefer_nick: str = "") -> PresenceOutcome:
    worker = parse_worker_nick(nick)
    if worker:
        mid, pid = worker
        return delete_worker(home, mid, pid, briefer_nick)
    mid = machine_from_nick(nick)
    if mid:
        return shop_down(home, mid, briefer_nick)
    return PresenceOutcome(ok=True)


def apply_callback(home: Path, payload: dict, briefer_nick: str = "") -> CallbackOutcome:
    """Apply a BobCallback report/git-claim op.

    FR #2902: ``git-claim`` must not run under ``digest.lock`` - ``claim_top`` can wait
    on ``git-claim.lock`` for up to ``LOCK_WAIT_S`` (30s) while chair resync/purge holds
    it, which aged ``digest.lock`` past ``lock_stale_s`` and made ``/health`` 503.
    Digest mutators still take ``digest.lock`` via ``_apply_callback_digest``.
    """
    # FR #69: chair --home is ~/.jeeves; digest.json + ChanServ roster live in BOB_DIGEST_HOME.
    home = fleet_digest_home(Path(home))
    if not isinstance(payload, dict):
        return CallbackOutcome(ok=False, err="malformed")
    if any(k.lower() in ("secret", "x-bob-secret", "password") for k in payload):
        return CallbackOutcome(ok=False, err="secret")
    blob = json.dumps(payload, separators=(",", ":"))
    if looks_like_secret(blob):
        return CallbackOutcome(ok=False, err="secret")
    op = str(payload.get("op") or "").strip().lower()
    if op == "git-claim":
        import gitclaim

        status, job = gitclaim.claim_top(
            home,
            str(payload.get("nick") or ""),
            str(payload.get("channel") or ""),
        )
        if status == "error":
            return CallbackOutcome(ok=False, err="queue")
        body = json.dumps({"ok": True, "claimed": job}, separators=(",", ":")).encode("utf-8")
        return CallbackOutcome(ok=True, changed=job is not None, body=body)
    return _apply_callback_digest(home, payload, briefer_nick, op)


@_digest_locked
def _apply_callback_digest(
    home: Path, payload: dict, briefer_nick: str, op: str
) -> CallbackOutcome:
    mid = normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
    if mid:
        mid = fold_machine_id(mid)       # #79: reports from a legacy alias land on the canonical machine
    actions: list[str] = []
    if op == "merge":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        if not is_roster_machine(home, mid):
            return CallbackOutcome(ok=False, err="not registered")
        pid_raw = payload.get("pid")
        if pid_raw is not None and str(pid_raw) != "" and "working_on" in payload:
            try:
                str(int(str(pid_raw)))
            except ValueError:
                return CallbackOutcome(ok=False, err="bad pid")
            text = str(payload.get("working_on") or "").strip()
            idle = str(payload.get("state") or "").strip().lower() == "idle"
            if not text and not idle:
                return CallbackOutcome(ok=False, err="working_on required")
            if looks_like_secret(text):
                return CallbackOutcome(ok=False, err="secret")
        doc = load_digest(home)
        ent_before = copy.deepcopy(_machine_entry(doc, mid))
        fp_before = _machine_fingerprint(ent_before)
        pools_before = copy.deepcopy(doc.get("cursor_pools"))
        if isinstance(payload.get("cursor_pools"), list):
            # #41: per-machine rows live in machines.<id>.cursor_pools (see _apply_merge_payload);
            # a machine report must never replace/clear the fleet-wide list. Drop the legacy
            # fleet list once machines report their own so it cannot go stale.
            doc.pop("cursor_pools", None)
        actions = _apply_merge_payload(doc, mid, payload)
        fp_after = _machine_fingerprint(_machine_entry(doc, mid))
        pools_after = doc.get("cursor_pools")
        if fp_before == fp_after and pools_before == pools_after:
            return CallbackOutcome(ok=True, changed=False, actions=[])
        if briefer_nick:
            doc["briefer"] = briefer_nick
        doc["ts"] = _utc_now_iso()
        _note_event(doc, "merge", machine=mid)
        save_digest(home, doc)
        return CallbackOutcome(ok=True, actions=actions)
    if op in ("worker-upsert", "worker-remove", "worker-work"):
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        if not is_roster_machine(home, mid):
            return CallbackOutcome(ok=False, err="not registered")
        return _apply_worker_op(home, op, mid, payload, briefer_nick)
    if op == "delete-worker":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        out = delete_worker(home, mid, payload.get("pid") or "", briefer_nick)
        if out.ok and out.actions:
            actions.extend(out.actions)
        if out.ok:
            return CallbackOutcome(ok=True, actions=actions)
        return CallbackOutcome(ok=False, err=out.err or "bad delete")
    if op == "shop-down":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
        out = shop_down(home, mid, briefer_nick)
        if out.ok and out.actions:
            actions.extend(out.actions)
        if out.ok:
            return CallbackOutcome(ok=True, actions=actions)
        return CallbackOutcome(ok=False, err=out.err or "bad shop-down")
    return CallbackOutcome(ok=False, err="bad op")


def _github_actor(payload: dict) -> str:
    for key in ("sender", "pusher"):
        ent = payload.get(key)
        if isinstance(ent, dict):
            name = str(ent.get("login") or ent.get("name") or "").strip()
            if name:
                return name
    return ""


def _github_repo_name(payload: dict) -> str:
    repo = payload.get("repository")
    if isinstance(repo, dict):
        return str(repo.get("full_name") or repo.get("name") or "").strip()
    return ""


def format_github_webhook_announce(event: str, payload: dict) -> str:
    """Single fleet line for digest chair (Jeeves) on #bobiverse."""
    ev = (event or "").strip().lower()
    repo = _github_repo_name(payload)
    actor = _github_actor(payload)
    bits: list[str] = [ev]
    if repo:
        bits.append(repo)
    if ev == "ping":
        zen = str(payload.get("zen") or "").strip()
        if zen:
            bits.append(zen[:80])
    elif ev == "push":
        ref = str(payload.get("ref") or "").strip()
        if ref.startswith("refs/heads/"):
            ref = ref[len("refs/heads/") :]
        if ref:
            bits.append(ref)
        after = str(payload.get("after") or "").strip()
        if after:
            bits.append(after[:12])
        commits = payload.get("commits")
        if isinstance(commits, list) and commits:
            bits.append(f"{len(commits)} commit(s)")
    elif ev == "pull_request":
        pr = payload.get("pull_request")
        if isinstance(pr, dict):
            action = str(payload.get("action") or "").strip()
            if action:
                bits.append(action)
            num = pr.get("number")
            if num is not None:
                bits.append(f"#{num}")
            title = str(pr.get("title") or "").strip()
            if title:
                bits.append(title[:120])
    elif ev == "issues":
        issue = payload.get("issue")
        if isinstance(issue, dict):
            action = str(payload.get("action") or "").strip()
            if action:
                bits.append(action)
            num = issue.get("number")
            if num is not None:
                bits.append(f"#{num}")
            title = str(issue.get("title") or "").strip()
            if title:
                bits.append(title[:120])
    else:
        action = str(payload.get("action") or "").strip()
        if action:
            bits.append(action)
    if actor:
        bits.append(f"by {actor}")
    line = GIT_ANNOUNCE_PREFIX + " ".join(p for p in bits if p)
    if len(line) > MAX_GIT_ANNOUNCE:
        line = line[: MAX_GIT_ANNOUNCE - 1] + "…"
    return line


def enqueue_chair_fleet_privmsg(home: Path, body: str, channel: str = FLEET_CHANNEL) -> bool:
    """Append PRIVMSG to chair-outbox.txt. Only irc_agent --chair drains it."""
    text = (body or "").replace("\r", " ").replace("\n", " ").strip()
    if not text or looks_like_secret(text):
        return False
    root = fleet_digest_home(Path(home))
    outbox = root / "chair-outbox.txt"
    try:
        outbox.parent.mkdir(parents=True, exist_ok=True)
        with outbox.open("a", encoding="utf-8") as fh:
            fh.write(f"PRIVMSG {channel} :{text}\n")
        return True
    except OSError:
        return False


def apply_git_webhook(home: Path, event: str, payload: dict) -> GitWebhookOutcome:
    """Announce path only — never secret-scan the full GitHub JSON body (FR #206)."""
    if not (event or "").strip():
        return GitWebhookOutcome(ok=False, err="no event")
    if not isinstance(payload, dict):
        return GitWebhookOutcome(ok=False, err="malformed")
    line = format_github_webhook_announce(event, payload)
    if not line.startswith(GIT_ANNOUNCE_PREFIX):
        return GitWebhookOutcome(ok=False, err="announce")
    hit = secret_marker_hit(line)
    if hit:
        line = redact_git_announce_line(line, hit)
    import gitclaim
    import github_api_budget as gab

    claim = gitclaim.claim_from_payload(event, payload, line=line)
    if claim is not None:
        queued = gitclaim.enqueue_unaccepted(home, claim)
        # FR #1811: surface queue-lock-timeout / queue-read / queue-write (claim also spooled).
        if isinstance(queued, str) and queued.startswith("error"):
            err = queued.split(":", 1)[1] if ":" in queued else "queue"
            return GitWebhookOutcome(ok=False, err=err or "queue")
    # FR #3212: stamp delivery time for gap-triggered reconcile (even announce-only events).
    gab.stamp_git_webhook(home)
    if not enqueue_chair_fleet_privmsg(home, line):
        return GitWebhookOutcome(ok=False, err="outbox")
    return GitWebhookOutcome(ok=True, announced=True)


def route_cc(kind: str, pm_open: bool) -> frozenset[str]:
    k = (kind or "").strip().lower().replace("-", "_")
    if k in ("secret", "secrets", "secrets_shaped"):
        return frozenset()
    if k in ("thinking", "tool", "tool_xscr", "trace", "transcript"):
        return frozenset({CC_QUERY}) if pm_open else frozenset()
    if k in ("assistant", "stdout", "visible"):
        dest = {CC_SHOP}
        if pm_open:
            dest.add(CC_QUERY)
        return frozenset(dest)
    if k in ("working_on",):
        # Issue #167: status is webhook-only; never IRC shop or Query.
        return frozenset()
    return frozenset()


def working_on_shop_line(nick: str, text: str) -> str:
    return f"{nick}: {WORKING_ON_PREFIX}{text}"


def parse_working_on_shop_line(body: str) -> tuple[str | None, str] | None:
    """Parse shop PRIVMSG body; return (nick or None, job text)."""
    text = (body or "").strip()
    if not text:
        return None
    if WORKING_ON_SHOP_SEP in text:
        left, job = text.split(WORKING_ON_SHOP_SEP, 1)
        nick = left.strip()
        job = job.strip()
        if nick and parse_worker_nick(nick) and job:
            return nick, job
        return None
    if text.startswith(WORKING_ON_PREFIX):
        job = text[len(WORKING_ON_PREFIX) :].strip()
        return (None, job) if job else None
    return None


def ingest_working_on_shop(
    home: Path, sender_nick: str, body: str, briefer_nick: str = ""
) -> PresenceOutcome:
    parsed = parse_working_on_shop_line(body)
    if not parsed:
        return PresenceOutcome(ok=False, err="not working_on")
    nick_in_line, job = parsed
    who = (nick_in_line or sender_nick or "").strip()
    worker = parse_worker_nick(who)
    if not worker:
        return PresenceOutcome(ok=False, err="not worker")
    mid, pid = worker
    out = merge_worker_working_on(home, mid, pid, job, briefer_nick)
    if not out.ok:
        return out
    if out.actions:
        return out
    action = f"'s pid {pid} on {mid} is working on {job.strip()}"
    return PresenceOutcome(ok=True, actions=[action], machine_id=mid)


def split_irc_text(text: str, limit: int = MAX_DIGEST_LINE) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    if looks_like_secret(raw):
        return []
    if len(raw) <= limit:
        return [raw]
    return [raw[i : i + limit] for i in range(0, len(raw), limit)]


def machine_english(ent: dict) -> str:
    mid = bobtalk.display_id(str(ent.get("id") or "?"))
    if not ent.get("online"):
        return f"{mid}: I am offline"
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    for pid, w in workers.items():
        wo = str((w or {}).get("working_on") or "").strip()
        if wo:
            return f"{mid}: working on {wo} (pid {pid})"
    wo = str(ent.get("working_on") or "").strip()
    if wo:
        return f"{mid}: working on {wo}"
    return f"{mid}: I am online (idle)"


def english_summary_lines(home: Path) -> list[str]:
    doc = load_digest(home)
    lines: list[str] = []
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    for mid in roster_machine_ids(home):
        ent = machines.get(mid)
        if isinstance(ent, dict):
            lines.append(machine_english(ent))
    return lines


def _normalize_job_entry(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    repo = str(raw.get("repo") or "").strip()
    state = str(raw.get("state") or "running").strip() or "running"
    entry = {
        "repo": repo,
        "sha": str(raw.get("sha") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "description": str(raw.get("description") or raw.get("desc") or "").strip(),
        "state": state,
        "run_time": str(raw.get("run_time") or raw.get("runtime") or "").strip(),
    }
    blob = json.dumps(entry, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return entry


def _normalize_jobs_list(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        norm = _normalize_job_entry(item)
        if norm is not None:
            out.append(norm)
    return out


def _pool_reject_machine_ids() -> set[str]:
    """Ids that are machines/seats, not pools (old rows carried ``seat: <machine>``)."""
    ids = set(SHORT_ID) | set(ID_ALIASES) | set(seat_machine_ids())
    return ids


def _normalize_cursor_pool_id(raw: object) -> str | None:
    if raw is None:
        return None
    key = str(raw).strip()
    if not key:
        return None
    lower = key.lower()
    if lower in _XAI_SEAT_LABELS:
        return None
    if lower in _CURSOR_POOL_ID_ALIASES:
        return _CURSOR_POOL_ID_ALIASES[lower]
    if lower in CURSOR_POOL_IDS:
        return lower
    if lower in _pool_reject_machine_ids():
        return None
    if lower in _CURSOR_POOL_ID_ALIASES.values():
        return lower
    return key


def _official_cursor_pool_label(pool_id: str, raw_label: object) -> str:
    official = CURSOR_POOL_LABEL_BY_ID.get(pool_id)
    if official:
        return official
    label = str(raw_label or "").strip()
    if label and label.lower() not in _XAI_SEAT_LABELS:
        return label
    return pool_id


def _coerce_cursor_pool(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    # #41: accept BOTH the server row shape (group/id, remaining) and bob's wire row shape
    # (group_id, group_label, remaining_pct, period_end) from ConvertTo-BobDigestCursorPoolRows.
    pool_id = _normalize_cursor_pool_id(raw.get("group") or raw.get("group_id") or raw.get("id"))
    if not pool_id:
        pool_id = _normalize_cursor_pool_id(raw.get("seat"))
    if not pool_id:
        return None
    label = _official_cursor_pool_label(pool_id, raw.get("label") or raw.get("group_label"))
    if label.lower() in _XAI_SEAT_LABELS:
        return None
    remaining = raw.get("remaining")
    if remaining is None:
        remaining = raw.get("remaining_pct")
    if remaining is None:
        remaining = raw.get("used")
    if remaining is not None:
        try:
            remaining = int(float(remaining))
        except (TypeError, ValueError):
            remaining = None
        if remaining is not None and not 0 <= remaining <= 100:
            remaining = None
    period = raw.get("period_end") or raw.get("reset")
    overage = raw.get("overage")
    if overage is not None:
        overage = str(overage)
    entry = {
        "id": pool_id,
        "seat": pool_id,
        "label": label,
        "remaining": remaining,
        "period_end": str(period) if period else None,
        "reset": str(raw.get("reset") or period or "") or None,
        "overage": overage,
    }
    # #114: registered account/channel identity the tray needs on each pool row.
    machine_id = raw.get("machine_id") or raw.get("machine")
    if machine_id is not None and str(machine_id).strip():
        mid = normalize_machine_id(str(machine_id)) or str(machine_id).strip().lower()
        entry["machine_id"] = mid
    account = raw.get("account") or raw.get("nick")
    if account is not None and str(account).strip():
        entry["account"] = str(account).strip()
    channel = raw.get("channel") or raw.get("shop")
    if channel is not None and str(channel).strip():
        ch = str(channel).strip()
        if not ch.startswith("#"):
            ch = f"#{ch.lstrip('#')}"
        entry["channel"] = ch
    blob = json.dumps(entry, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return entry


def _canonical_pool_account(mid: str) -> str:
    """FR #976: pool account is bob-<canonical-mid>, never a legacy NICK_TO_MACHINE alias (bob-ionos)."""
    norm = normalize_machine_id(mid) or (str(mid).strip().lower() if mid else "")
    if not norm:
        return ""
    if norm == "ce-priority-dev1":
        return "bob-dev1"
    return f"bob-{norm}"


def _stamp_pool_identity(row: dict, mid: str, *, account: str | None = None, channel: str | None = None) -> dict:
    """#114: ensure machine_id / account / channel on a coerced pool row.

    FR #976: always stamp bob-<canonical-mid> (overwrite legacy aliases such as
    bob-ionos left on the row by older reporters / nick_for_machine).
    """
    if not isinstance(row, dict):
        return row
    norm = normalize_machine_id(mid) or (str(mid).strip().lower() if mid else "")
    if norm and not row.get("machine_id"):
        row["machine_id"] = norm
    canonical = _canonical_pool_account(norm) if norm else ""
    explicit = (account or "").strip()
    # Drop legacy aliases even when passed as the explicit account from ent.nick.
    if explicit and explicit in NICK_TO_MACHINE:
        explicit = ""
    if explicit and canonical and explicit.startswith("bob-") and explicit != canonical:
        # Explicit bob-* that is not the canonical mid nick is a legacy alias — ignore.
        if NICK_TO_MACHINE.get(explicit) == norm or explicit == "bob-ionos":
            explicit = ""
    acct = explicit or canonical
    if acct:
        row["account"] = acct
    ch = (channel or "").strip()
    if not ch and norm:
        try:
            ch = shop_channel(norm)
        except ValueError:
            ch = f"#{norm}"
    if ch and not row.get("channel"):
        if not ch.startswith("#"):
            ch = f"#{ch.lstrip('#')}"
        row["channel"] = ch
    return row


def _coerce_cursor_pools(raw: object, *, machine_id: str | None = None) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        pool = _coerce_cursor_pool(item)
        if not pool:
            continue
        if machine_id:
            pool = _stamp_pool_identity(pool, machine_id)
        pid = str(pool.get("id") or "")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pool)
    return out


def _peer_fill_keys() -> tuple[str, ...]:
    return _MERGE_PEER_FIELDS


def _mask_expired_pools(base: dict, now: datetime | None = None) -> None:
    """#40: a pool whose billing/weekly period has ended is UNKNOWN (null), never its old value.

    Mutates ``base`` (a private copy): expired pcent keys become None, weekly -> None when the
    weekly period ended, overage_gbp -> None when the Cursor billing period ended.
    Missing period_end => cannot tell => values are left alone.
    """
    pcent = base.get("pcent")
    if isinstance(pcent, dict) and pcent:
        masked = dict(pcent)
        for pool_id, aliases in _PCENT_KEYS_BY_POOL.items():
            pe, _ = _cursor_pool_period(base, pool_id)
            if not _period_expired(pe, now):
                continue
            for key in aliases:
                if key in masked:
                    masked[key] = None
        if _period_expired(base.get("period_end"), now):
            for key in _GROK_WEEKLY_EXTRA_PCENT_KEYS:
                if key in masked:
                    masked[key] = None
        base["pcent"] = masked
    if base.get("weekly") is not None and _period_expired(base.get("period_end"), now):
        base["weekly"] = None
    rows = base.get("cursor_pools")
    if isinstance(rows, list):
        masked_rows = []
        for row in rows:
            row = dict(row)
            if row.get("remaining") is not None and _period_expired(row.get("period_end"), now):
                row["remaining"] = None  # expired window => unknown, never the old value / 0
                row["overage"] = None
            masked_rows.append(row)
        base["cursor_pools"] = masked_rows
    cpe, _ = _cursor_pool_period(base, "cursor-models")
    if base.get("overage_gbp") not in (None, "") and _period_expired(cpe, now):
        base["overage_gbp"] = None


def export_machine_for_tray(
    home: Path, mid: str, ent: dict, now: datetime | None = None
) -> dict:
    """Tray-complete machine row: digest presence + bob-peers metrics."""
    base = _coerce_machine(mid, ent)
    peer = bobstat.read_peer(home, mid)
    if peer:
        for key in _peer_fill_keys():
            if key not in peer or peer[key] is None or peer[key] == "":
                continue
            if key not in base or base.get(key) in (None, "", [], {}):
                base[key] = peer[key]
    for key in _peer_fill_keys():
        if key in ent and ent[key] is not None and ent[key] != "":
            base[key] = ent[key]
    try:
        base["running"] = int(base.get("running") or 0)
    except (TypeError, ValueError):
        base["running"] = 0
    try:
        base["queued"] = int(base.get("queued") or 0)
    except (TypeError, ValueError):
        base["queued"] = 0
    weekly = base.get("weekly")
    if weekly is not None and weekly != "":
        try:
            base["weekly"] = int(weekly)
        except (TypeError, ValueError):
            base["weekly"] = None
    else:
        base["weekly"] = None
    base["jobs"] = _normalize_jobs_list(base.get("jobs"))
    if base.get("period_end") in (None, ""):
        reset = base.get("reset")
        if reset:
            base["period_end"] = str(reset)
    _mask_expired_pools(base, now)
    # Prefer chair worker_list activity over a peer-blanked machine.working_on.
    _refresh_machine_activity_from_worker_list(base)
    out: dict = {}
    for key in _TRAY_MACHINE_EXPORT_KEYS:
        if key in base:
            out[key] = base[key]
    out.setdefault("id", mid)
    out.setdefault("nick", nick_for_machine({}, mid))
    out.setdefault("shop", shop_channel(mid))
    out.setdefault("online", False)
    out.setdefault("status", "I am offline" if not out.get("online") else "I am online")
    out.setdefault("working_on", "")
    out["workers"] = worker_list_for_export(base)
    out.setdefault("weekly", None)
    out.setdefault("period_end", None)
    out.setdefault("lastSeen", None)
    out.setdefault("running", 0)
    out.setdefault("queued", 0)
    out.setdefault("jobs", [])
    return out


def _cursor_pool_overage(ent: dict) -> str | None:
    for key in ("overage", "overspend", "cursor_overage", "cursor_overspend"):
        val = ent.get(key)
        if val is not None and str(val).strip():
            return str(val)
    gbp = ent.get("overage_gbp")
    if gbp not in (None, ""):
        try:
            return "\u00a3%.2f" % float(gbp)
        except (TypeError, ValueError):
            return None
    return None


def _cursor_pool_period(ent: dict, pool_id: str | None = None) -> tuple[str | None, str | None]:
    """Per-pool reset clock: grok-weekly/sand = Cursor Sand period end (NOT the xAI weekly ``period_end``,
    #80); else Cursor billing."""
    pid = str(pool_id or "").strip().lower()
    if pid in ("grok-weekly", "grok-chat", "sand", "cursor-grok-chat"):
        weekly = ent.get("sand_period_end") or ent.get("period_end")
        if weekly not in (None, ""):
            period_s = str(weekly)
            return period_s, period_s
        return None, None
    cursor_period = ent.get("cursor_period_end")
    if cursor_period in (None, ""):
        # Fall back to weekly only when billing end is unknown
        weekly = ent.get("period_end")
        if weekly not in (None, ""):
            period_s = str(weekly)
            return period_s, period_s
        return None, None
    period_s = str(cursor_period)
    return period_s, period_s


def _pcent_remaining_for_pool(pcent: dict, pool_id: str) -> int | None:
    for key in _PCENT_KEYS_BY_POOL.get(pool_id, (pool_id,)):
        raw = pcent.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def _lesser_int(a: object, b: object) -> int | None:
    """Lesser remaining % wins when the same account is reported from many boxes (#174)."""
    vals: list[int] = []
    for raw in (a, b):
        if raw is None or raw == "":
            continue
        try:
            vals.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not vals:
        return None
    return min(vals)


def _merge_pcent_lesser(existing: object, incoming: dict, *, replace: bool = False) -> dict:
    """Lesser remaining within a period; replace entirely when billing period rolled."""
    if replace or not isinstance(existing, dict) or not existing:
        return dict(incoming)
    out: dict = {}
    out.update(existing)
    for key, val in incoming.items():
        if key in out:
            lesser = _lesser_int(out.get(key), val)
            if lesser is not None:
                out[key] = lesser
                continue
        out[key] = val
    return out


POOL_STALE_AFTER_S = 6 * 3600.0     # #80: a machine not heard from for this long no longer speaks for the pool


def _machine_counts_for_pools(mid: object, ent: dict, now: datetime | None = None) -> bool:
    """#80: only a live machine's number may set the fleet pool minimum.

    Excluded: legacy alias keys (``ionos`` -> win-mpre8vi4u6u), machines that are offline, and machines whose
    ``lastSeen`` is older than ``POOL_STALE_AFTER_S``. (A missing/unparseable lastSeen is not evidence of staleness.)
    """
    if is_alias_machine_id(mid):
        return False
    if not ent.get("online"):
        return False
    seen = _parse_iso_ts(ent.get("lastSeen"))
    if seen is not None:
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=timezone.utc)
        ref = now or datetime.now(timezone.utc)
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        if (ref - seen).total_seconds() > POOL_STALE_AFTER_S:
            return False
    return True


def _lesser_machine_pcent_for_pool(
    machines: dict[str, dict], pool_id: str, now: datetime | None = None
) -> tuple[int | None, dict | None]:
    """Pick the lesser remaining % across LIVE machines (shared account SoT, #174; offline/stale/alias: #80)."""
    best_rem: int | None = None
    best_ent: dict | None = None
    mids = [m for m in machines.keys() if normalize_machine_id(str(m))]
    for mid in mids:
        ent = machines.get(mid) or {}
        if not _machine_counts_for_pools(mid, ent, now):
            continue
        pcent = ent.get("pcent") if isinstance(ent.get("pcent"), dict) else {}
        rem = _pcent_remaining_for_pool(pcent, pool_id)
        if rem is None:
            continue
        if best_rem is None or rem < best_rem:
            best_rem = rem
            best_ent = ent
    return best_rem, best_ent


def _pcent_key_present(pcent: object, pool_id: str) -> bool:
    if not isinstance(pcent, dict):
        return False
    return any(k in pcent for k in _PCENT_KEYS_BY_POOL.get(pool_id, (pool_id,)))


def _finalize_pool(row: dict, now: datetime | None) -> dict:
    """#40/#41: stamp state; expired period or no value => remaining None (unknown, not 0)."""
    if row.get("remaining") is not None and _period_expired(row.get("period_end"), now):
        row["remaining"] = None
        row["overage"] = None
        row["state"] = "unknown"
        row["reason"] = "period-expired"
        return row
    if row.get("remaining") is None:
        row["state"] = "unknown"
        row["reason"] = row.get("reason") or "no-data"
        if _period_expired(row.get("period_end"), now):
            row["overage"] = None
            row["reason"] = "period-expired"
    else:
        row["state"] = "current"
        row.pop("reason", None)
    return row


def build_cursor_pools(
    doc: dict, machines: dict[str, dict], now: datetime | None = None
) -> list[dict]:
    stored = _coerce_cursor_pools(doc.get("cursor_pools"))
    if stored:
        # Still force lesser across live machine pcent when both exist (#174).
        rebuilt: list[dict] = []
        for pool in stored:
            if not isinstance(pool, dict):
                continue
            pid = str(pool.get("id") or "")
            rem_m, ent = _lesser_machine_pcent_for_pool(machines, pid, now) if pid else (None, None)
            row = dict(pool)
            if rem_m is not None:
                pe, reset = (None, None)
                if ent:
                    pe, reset = _cursor_pool_period(ent, pid)
                rolled = _period_rolled(row.get("period_end"), pe)
                if rolled:
                    row["remaining"] = rem_m
                    if pe:
                        row["period_end"] = pe
                        row["reset"] = reset
                else:
                    cur = row.get("remaining")
                    lesser = _lesser_int(cur, rem_m)
                    if lesser is not None:
                        row["remaining"] = lesser
                    if ent and row.get("period_end") in (None, ""):
                        row["period_end"] = pe
                        row["reset"] = reset
            rebuilt.append(_finalize_pool(row, now))
        return rebuilt
    pools: list[dict] = []
    for pool_id, label in CURSOR_SPENDING_POOLS:
        remaining, ent = _lesser_machine_pcent_for_pool(machines, pool_id, now)
        if remaining is None:
            # #40: a machine that reported this pool but whose value was masked as
            # expired (None) still yields an explicit UNKNOWN row, not a missing/zero one.
            holder = None
            for mid in machines:
                e = machines.get(mid) or {}
                if is_alias_machine_id(mid):
                    continue            # a live pool with no live reporter is UNKNOWN, but never via the alias
                if _pcent_key_present(e.get("pcent"), pool_id):
                    holder = e
                    break
            if holder is None:
                continue
            ent = holder
        period_end, reset = (None, None)
        overage = None
        if ent:
            period_end, reset = _cursor_pool_period(ent, pool_id)
            if pool_id == "on-demand":
                overage = _cursor_pool_overage(ent)
        pools.append(
            _finalize_pool(
                {
                    "id": pool_id,
                    "seat": pool_id,
                    "label": label,
                    "remaining": remaining,
                    "period_end": period_end,
                    "reset": reset,
                    "overage": overage,
                },
                now,
            )
        )
    return pools


# FR #2729: the report is read-only; never queue behind the git-claim lock to purge.
REPORT_PURGE_LOCK_WAIT_S = 0.2


def _public_queue(home: Path) -> dict:
    """Job list served on GET /bob/v1/report. Webhook mirror, not a side channel."""
    import gitclaim

    # FR #2458: surface-heal stale merged/closed MRB before digest consumers see them.
    # Prefer open-only GitHub checker when token/home allow; otherwise ledger/merged flags only.
    # FR #2729: shared 60 s verdict cache (not a fresh dict per GET); GitHub is asked outside
    # the queue lock; skip the purge when the lock is not free within REPORT_PURGE_LOCK_WAIT_S.
    with contextlib.suppress(Exception):
        checker = gitclaim.github_pr_exists_checker(
            home=home, cache=gitclaim.PR_EXISTS_SHARED_CACHE
        )
        gitclaim.purge_dead_mrb_rows(
            home, pr_exists=checker, lock_timeout=REPORT_PURGE_LOCK_WAIT_S
        )
    doc = gitclaim.load_queue(home)
    return {
        "unaccepted": list(doc.get("unaccepted") or []),
        "accepted": list(doc.get("accepted") or []),
    }


def build_digest_object(home: Path, briefer_nick: str, now: datetime | None = None) -> dict:
    """GET /bob/v1/report payload: ChanServ roster shops only + chair_channels."""
    doc = load_digest(home)
    roster = list(roster_machine_ids(home))
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    cleaned: dict[str, dict] = {}
    for mid, ent in sorted(machines.items(), key=lambda kv: is_alias_machine_id(kv[0])):   # canonical first
        coerced = _coerce_machine(str(mid), ent)
        cid = fold_machine_id(coerced["id"])
        coerced["id"] = cid
        if cid in roster and cid not in cleaned:
            cleaned[cid] = coerced
    for mid in roster:
        cleaned.setdefault(mid, _empty_machine(mid))
    exported: dict[str, dict] = {}
    for mid in roster:
        exported[mid] = export_machine_for_tray(
            home, mid, cleaned.get(mid) or _empty_machine(mid), now
        )
    chair = (os.environ.get(CHAIR_NICK_ENV) or "").strip() or str(
        doc.get("chairNick") or doc.get("chair_nick") or ""
    ).strip()
    briefer = (briefer_nick or str(doc.get("briefer") or "")).strip()
    channels = chair_channels(home)
    return {
        "v": int(doc.get("v") or 1),
        "ts": str(doc.get("ts") or _utc_now_iso()),
        "briefer": briefer,
        "chairNick": chair or briefer,
        "machines": exported,
        "roster_machine_ids": sorted(roster),
        "chair_channels": channels,
        "cursor_pools": build_cursor_pools(doc, exported, now),
        "queue": _public_queue(home),
    }


def _chunk_json(raw: str) -> list[str]:
    if len(raw) <= MAX_DIGEST_LINE:
        return [raw]
    chunks: list[str] = []
    n = (len(raw) + MAX_DIGEST_LINE - 1) // MAX_DIGEST_LINE
    for i in range(n):
        piece = raw[i * MAX_DIGEST_LINE : (i + 1) * MAX_DIGEST_LINE]
        chunks.append(f"{DIGEST_PREFIX}{i + 1}/{n} {piece}")
    return chunks


def format_digest_whisper_lines(
    home: Path,
    briefer_nick: str,
    form: str = "full",
    machine_id: str | None = None,
    english: bool = True,
) -> list[str]:
    if form == "help":
        return HELP_TEXT.splitlines()
    if form == "machine":
        obj = build_digest_object(home, briefer_nick)
        mid = normalize_machine_id(machine_id or "")
        if not mid or mid not in obj["machines"]:
            return [NO_MACHINE]
        raw = json.dumps(obj["machines"][mid], separators=(",", ":"), sort_keys=True)
        return _chunk_json(raw)
    lines: list[str] = []
    if english:
        lines.extend(english_summary_lines(home))
    raw = json.dumps(build_digest_object(home, briefer_nick), separators=(",", ":"), sort_keys=True)
    lines.extend(_chunk_json(raw))
    return lines


_PEER_DELTA_SKIP = frozenset({"lastSeen", "ts"})


def should_periodic_bobiverse_pull(nick: str, *, chair: bool = False) -> bool:
    """Fleet bob-* Watch seats pull digest; talk seats and workers do not (issue #129)."""
    import talk_seat_pid

    if chair:
        return False
    if not bobtalk.is_fleet_bob_nick(nick):
        return False
    if talk_seat_pid.parse_talk_seat_nick(nick):
        return False
    if parse_worker_nick(nick):
        return False
    return True


class DigestWhisperAssembler:
    """Reassemble BOB DIGEST v1 i/n whisper lines into one JSON object."""

    def __init__(self) -> None:
        self._from: str | None = None
        self._parts: dict[int, tuple[int, str]] = {}

    def reset(self) -> None:
        self._from = None
        self._parts = {}

    def feed(self, from_nick: str, text: str) -> dict | None:
        raw = (text or "").strip()
        if not raw:
            return None
        who = (from_nick or "").strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                return None
            self.reset()
            return obj if isinstance(obj, dict) else None
        if not raw.startswith(DIGEST_PREFIX):
            return None
        rest = raw[len(DIGEST_PREFIX) :]
        if " " not in rest:
            return None
        head, piece = rest.split(" ", 1)
        if "/" not in head:
            return None
        try:
            i_s, n_s = head.split("/", 1)
            i = int(i_s)
            n = int(n_s)
        except ValueError:
            return None
        if n < 1 or i < 1 or i > n:
            return None
        if self._from and who.lower() != self._from.lower():
            self.reset()
        self._from = who
        self._parts[i] = (n, piece)
        if len(self._parts) != n or not all(j in self._parts for j in range(1, n + 1)):
            return None
        blob = "".join(self._parts[j][1] for j in range(1, n + 1))
        self.reset()
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            return None
        return obj if isinstance(obj, dict) else None


def _delta_norm(key: str, val: object) -> object:
    if key in ("running", "queued", "weekly"):
        if val in (None, "", "-"):
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return val
    if key == "jobs":
        if not isinstance(val, list):
            return val
        return json.dumps(_normalize_jobs_list(val), sort_keys=True, separators=(",", ":"))
    if key == "pcent" and isinstance(val, dict):
        return json.dumps(val, sort_keys=True, separators=(",", ":"))
    if val in (None, ""):
        return None
    return val


def _peer_delta_value(peer: dict, chair: dict, key: str) -> object | None:
    pv = peer.get(key)
    cv = chair.get(key)
    if _delta_norm(key, pv) == _delta_norm(key, cv):
        return None
    if pv in (None, ""):
        return None
    if looks_like_secret(str(pv)):
        return None
    return pv


def merge_payload_local_peer_ahead_of_chair(
    home: Path, machine_id: str, chair_machine: dict
) -> dict | None:
    """Build change-only webhook merge when local bob-peer differs from chair digest (#129)."""
    mid = normalize_machine_id(machine_id)
    if not mid or not isinstance(chair_machine, dict):
        return None
    peer = bobstat.read_peer(home, mid)
    if not peer:
        return None
    payload: dict = {"op": "merge", "machine": mid}
    changed = False
    for key in _MERGE_PEER_FIELDS:
        if key in _PEER_DELTA_SKIP:
            continue
        val = _peer_delta_value(peer, chair_machine, key)
        if val is not None:
            payload[key] = val
            changed = True
    for key in ("online", "status", "working_on"):
        val = _peer_delta_value(peer, chair_machine, key)
        if val is not None:
            payload[key] = val
            changed = True
    if not changed:
        return None
    blob = json.dumps(payload, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return payload


@_digest_locked
def ingest_fleet_digest_pull(home: Path, pull: dict) -> None:
    """Apply chair !bobiverse JSON to local digest.json and bob-peers (tray pull)."""
    if not isinstance(pull, dict):
        return
    machines = pull.get("machines")
    if not isinstance(machines, dict):
        return
    doc = load_digest(home)
    for key in ("v", "ts", "briefer", "chairNick", "chair_nick"):
        if key in pull and pull[key] not in (None, ""):
            doc[key] = pull[key]
    if isinstance(pull.get("cursor_pools"), list):
        doc["cursor_pools"] = _coerce_cursor_pools(pull["cursor_pools"])
    merged = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    for raw_mid, ent in machines.items():
        mid = normalize_machine_id(str(raw_mid))
        if not mid or not isinstance(ent, dict):
            continue
        merged[mid] = copy.deepcopy(ent)
    doc["machines"] = merged
    save_digest(home, doc)
    for raw_mid, ent in machines.items():
        mid = normalize_machine_id(str(raw_mid))
        if not mid or not isinstance(ent, dict):
            continue
        peer_doc: dict = {"id": mid}
        for key in _MERGE_PEER_FIELDS:
            if key in ent and ent[key] not in (None, ""):
                peer_doc[key] = ent[key]
        for key in ("online", "status", "working_on", "nick"):
            if key in ent and ent[key] not in (None, ""):
                peer_doc[key] = ent[key]
        if len(peer_doc) > 1:
            peer_doc["ok"] = True
            bobstat.write_peer(home, peer_doc)
