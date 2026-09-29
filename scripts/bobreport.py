#!/usr/bin/env python3
"""Shop-channel digest + public HTTP digest reader (issue #174). !bobiverse removed."""
from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import bobstat
import bobtalk

REPORT_CMD = "!report"
REPORT_GONE = "ERR report gone — use callback or GET /bob/v1/report"
NO_MACHINE = "ERR no such machine"
DEFAULT_DIGEST_URL = "https://irc.ntsa.uk/bob/v1/report"
DIGEST_URL_ENV = "AGENTIC_IRC_DIGEST_URL"
BOBIVERSE_GONE = "ERR !bobiverse gone — GET https://irc.ntsa.uk/bob/v1/report"
DIGEST_PREFIX = "BOB DIGEST v1 "
MAX_DIGEST_LINE = 350
FLEET_CHANNEL = "#bobiverse"
ACTION_COOLDOWN_S = 30.0
DISCONNECT_DEDUPE_S = 30.0
ID_ALIASES = {"dev1": "ce-priority-dev1", "ce-priority-dev1": "ce-priority-dev1"}

NICK_TO_MACHINE: dict[str, str] = {
    "bob-flamingo": "flamingo",
    "bob-marchhare": "marchhare",
    "bob-ionos": "ionos",
    "bob-dev1": "ce-priority-dev1",
}

SHORT_ID: dict[str, str] = {
    "flamingo": "fl",
    "marchhare": "mh",
    "ionos": "io",
    "ce-priority-dev1": "d1",
}
SHORT_TO_MACHINE = {v: k for k, v in SHORT_ID.items()}
FLEET_MACHINE_IDS = ("flamingo", "marchhare", "ionos", "ce-priority-dev1")
_FLEET_MACHINE_ID_SET = frozenset(FLEET_MACHINE_IDS)
CURSOR_SPENDING_POOLS: tuple[tuple[str, str], ...] = (
    ("cursor-models", "Cursor Models"),
    ("other-models", "Other Models"),
    ("grok-weekly", "Grok Weekly"),
    ("on-demand", "On-demand"),
)
CURSOR_POOL_IDS = frozenset(pid for pid, _ in CURSOR_SPENDING_POOLS)
CURSOR_POOL_LABEL_BY_ID = dict(CURSOR_SPENDING_POOLS)
_CURSOR_POOL_ID_ALIASES: dict[str, str] = {
    "cursor_models": "cursor-models",
    "cursor_models_remaining": "cursor-models",
    "low cost models": "cursor-models",
    "low-cost-models": "cursor-models",
    "high cost models": "other-models",
    "high-cost-models": "other-models",
    "other_models": "other-models",
    "grok chat": "grok-weekly",
    "grok-chat": "grok-weekly",
    "grok_chat": "grok-weekly",
    "grok_weekly": "grok-weekly",
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
    "grok-weekly": ("grok-weekly", "grok_weekly", "grok-chat", "grok_chat", "grok chat", "sand"),
    "on-demand": ("on-demand", "on_demand"),
}
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
    "kind",
    "cur",
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
    if mid not in SHORT_ID and mid not in ID_ALIASES:
        # accept registry ids even if extra, as long as they look like ids
        if mid not in FLEET_MACHINE_IDS:
            return mid if bobstat.ID_RE.match(mid) else None
    return mid


def machine_from_nick(nick: str) -> str | None:
    n = (nick or "").strip().lower()
    if n in NICK_TO_MACHINE:
        return NICK_TO_MACHINE[n]
    if n.startswith("bob-"):
        return normalize_machine_id(n[4:])
    return None


def parse_talk_seat_nick(nick: str) -> str | None:
    """{machine}-{agentPid} talk seat → machine id. Not bob-* / w-*."""
    n = (nick or "").strip().lower()
    if not n or n.startswith("bob-") or parse_worker_nick(n):
        return None
    for mid in sorted(FLEET_MACHINE_IDS, key=len, reverse=True):
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


def chair_channels() -> list[str]:
    """Jeeves / digest chair: bobosphere + every fleet shop (Simon 2026-09-22)."""
    shops = [shop_channel(mid) for mid in FLEET_MACHINE_IDS]
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

    BOB_DIGEST_HOME wins so Jeeves (--home ~/.agentic-irc-jeeves) drains
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
    }


def empty_digest() -> dict:
    return {
        "v": 1,
        "ts": "",
        "briefer": "",
        "machines": {mid: _empty_machine(mid) for mid in FLEET_MACHINE_IDS},
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
        }
    )
    if isinstance(raw.get("pcent"), dict):
        base["pcent"] = raw["pcent"]
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


def _ensure_seats(doc: dict) -> dict:
    machines = doc.setdefault("machines", {})
    if not isinstance(machines, dict):
        machines = {}
        doc["machines"] = machines
    for mid in FLEET_MACHINE_IDS:
        machines[mid] = _coerce_machine(mid, machines.get(mid))
    extra = [k for k in list(machines) if k not in FLEET_MACHINE_IDS]
    for mid in extra:
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
    return _ensure_seats(doc)


def save_digest(home: Path, doc: dict) -> None:
    path = digest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


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
    workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
    for w in workers.values():
        text = str((w or {}).get("working_on") or "").strip()
        if text:
            ent["working_on"] = text
            return
    ent["working_on"] = ""


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


CHAIR_NICK_ENV = "AGENTIC_IRC_CHAIR_NICK"


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
        "uptime_since": ent.get("uptime_since"),
        "workers": ent.get("workers"),
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
    if "pcent" in payload and isinstance(payload["pcent"], dict):
        ent["pcent"] = _merge_pcent_lesser(ent.get("pcent"), payload["pcent"])
    if payload.get("uptime_since"):
        ent["uptime_since"] = str(payload["uptime_since"])
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
        ent["working_on"] = str(payload.get("working_on") or "")
    for key in _MERGE_PEER_FIELDS:
        if key not in payload or payload[key] is None:
            continue
        val = payload[key]
        if key == "jobs" and not isinstance(val, list):
            continue
        if key == "pcent" and isinstance(val, dict):
            continue
        if key in ("weekly",) and val is not None:
            ent[key] = _lesser_int(ent.get(key), val)
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
    mid = normalize_machine_id(str(payload.get("machine") or payload.get("id") or ""))
    actions: list[str] = []
    if op == "merge":
        if not mid:
            return CallbackOutcome(ok=False, err="bad machine")
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
            doc["cursor_pools"] = _coerce_cursor_pools(payload["cursor_pools"])
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

    claim = gitclaim.claim_from_payload(event, payload, line=line)
    if claim is not None:
        queued = gitclaim.enqueue_unaccepted(home, claim)
        if queued == "error":
            return GitWebhookOutcome(ok=False, err="queue")
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
    for mid in FLEET_MACHINE_IDS:
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
    if lower in _FLEET_MACHINE_ID_SET or normalize_machine_id(lower) in _FLEET_MACHINE_ID_SET:
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
    pool_id = _normalize_cursor_pool_id(raw.get("group") or raw.get("id"))
    if not pool_id:
        pool_id = _normalize_cursor_pool_id(raw.get("seat"))
    if not pool_id:
        return None
    label = _official_cursor_pool_label(pool_id, raw.get("label"))
    if label.lower() in _XAI_SEAT_LABELS:
        return None
    remaining = raw.get("remaining")
    if remaining is None:
        remaining = raw.get("used")
    if remaining is not None:
        try:
            remaining = int(remaining)
        except (TypeError, ValueError):
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
    blob = json.dumps(entry, separators=(",", ":"))
    if looks_like_secret(blob):
        return None
    return entry


def _coerce_cursor_pools(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        pool = _coerce_cursor_pool(item)
        if not pool:
            continue
        pid = str(pool.get("id") or "")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pool)
    return out


def _peer_fill_keys() -> tuple[str, ...]:
    return _MERGE_PEER_FIELDS


def export_machine_for_tray(home: Path, mid: str, ent: dict) -> dict:
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
    out.setdefault("workers", {})
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
    return None


def _cursor_pool_period(ent: dict) -> tuple[str | None, str | None]:
    cursor_period = ent.get("cursor_period_end")
    if cursor_period in (None, ""):
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


def _merge_pcent_lesser(existing: object, incoming: dict) -> dict:
    out: dict = {}
    if isinstance(existing, dict):
        out.update(existing)
    for key, val in incoming.items():
        if key in out:
            lesser = _lesser_int(out.get(key), val)
            if lesser is not None:
                out[key] = lesser
                continue
        out[key] = val
    return out


def _lesser_machine_pcent_for_pool(
    machines: dict[str, dict], pool_id: str
) -> tuple[int | None, dict | None]:
    """Pick the lesser remaining % across machines (shared account SoT, #174)."""
    best_rem: int | None = None
    best_ent: dict | None = None
    for mid in FLEET_MACHINE_IDS:
        ent = machines.get(mid) or {}
        pcent = ent.get("pcent") if isinstance(ent.get("pcent"), dict) else {}
        rem = _pcent_remaining_for_pool(pcent, pool_id)
        if rem is None:
            continue
        if best_rem is None or rem < best_rem:
            best_rem = rem
            best_ent = ent
    return best_rem, best_ent


def build_cursor_pools(doc: dict, machines: dict[str, dict]) -> list[dict]:
    stored = _coerce_cursor_pools(doc.get("cursor_pools"))
    if stored:
        # Still force lesser across live machine pcent when both exist (#174).
        rebuilt: list[dict] = []
        for pool in stored:
            if not isinstance(pool, dict):
                continue
            pid = str(pool.get("id") or "")
            rem_m, ent = _lesser_machine_pcent_for_pool(machines, pid) if pid else (None, None)
            row = dict(pool)
            if rem_m is not None:
                cur = row.get("remaining")
                lesser = _lesser_int(cur, rem_m)
                if lesser is not None:
                    row["remaining"] = lesser
                if ent and row.get("period_end") in (None, ""):
                    pe, reset = _cursor_pool_period(ent)
                    row["period_end"] = pe
                    row["reset"] = reset
            rebuilt.append(row)
        return rebuilt
    pools: list[dict] = []
    for pool_id, label in CURSOR_SPENDING_POOLS:
        remaining, ent = _lesser_machine_pcent_for_pool(machines, pool_id)
        if remaining is None:
            continue
        period_end, reset = (None, None)
        overage = None
        if ent:
            period_end, reset = _cursor_pool_period(ent)
            if pool_id == "on-demand":
                overage = _cursor_pool_overage(ent)
        pools.append(
            {
                "id": pool_id,
                "seat": pool_id,
                "label": label,
                "remaining": remaining,
                "period_end": period_end,
                "reset": reset,
                "overage": overage,
            }
        )
    return pools


def _public_queue(home: Path) -> dict:
    """Job list served on GET /bob/v1/report. Webhook mirror, not a side channel."""
    import gitclaim

    doc = gitclaim.load_queue(home)
    return {
        "unaccepted": list(doc.get("unaccepted") or []),
        "accepted": list(doc.get("accepted") or []),
    }


def build_digest_object(home: Path, briefer_nick: str) -> dict:
    doc = load_digest(home)
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    cleaned: dict[str, dict] = {}
    for mid, ent in machines.items():
        coerced = _coerce_machine(str(mid), ent)
        cleaned[str(coerced["id"])] = coerced
    for mid in FLEET_MACHINE_IDS:
        cleaned.setdefault(mid, _empty_machine(mid))
    exported: dict[str, dict] = {}
    for mid in FLEET_MACHINE_IDS:
        exported[mid] = export_machine_for_tray(home, mid, cleaned[mid])
    chair = (os.environ.get(CHAIR_NICK_ENV) or "").strip() or str(
        doc.get("chairNick") or doc.get("chair_nick") or ""
    ).strip()
    briefer = (briefer_nick or str(doc.get("briefer") or "")).strip()
    return {
        "v": int(doc.get("v") or 1),
        "ts": str(doc.get("ts") or _utc_now_iso()),
        "briefer": briefer,
        "chairNick": chair or briefer,
        "machines": exported,
        "cursor_pools": build_cursor_pools(doc, exported),
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
