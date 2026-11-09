#!/usr/bin/env python3
"""Shop-channel digest + public HTTP digest reader (issue #174). !bobiverse removed."""
from __future__ import annotations

import contextlib
import copy
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
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
REPORT_GONE = "ERR report gone - use callback or GET /bob/v1/report"
NO_MACHINE = "ERR no such machine"
DEFAULT_DIGEST_URL = "https://bob.ntsa.uk/bob/v1/report"

# FR #6144: edge/WAF returns 403 to default Python-urllib User-Agent; ear digest
# pull then never POSTs fuel (stale weekly). Identify as bobreport explicitly.
DIGEST_HTTP_USER_AGENT = "Bobiverse-bobreport/1.0"
DIGEST_URL_ENV = "BOB_DIGEST_URL"
BOBIVERSE_GONE = "ERR !bobiverse gone - GET https://bob.ntsa.uk/bob/v1/report"
DIGEST_PREFIX = "BOB DIGEST v1 "
MAX_DIGEST_LINE = 350
FLEET_CHANNEL = "#bobiverse"
# FR #3834: shared registered airc/client control fallback; Bob ears also JOIN.
WONDERLAND_CHANNEL = "#wonderland"
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
    home (``BOB_DIGEST_HOME`` / ``~/.bobiverse``) - FR #69.
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
# Hosts with no Cursor login still publish these. grok-chat/sand is Cursor Sand,
# not xAI weekly, and must not ride along in this set.
_NON_CURSOR_PCENT_KEYS = ("grok-build", "opencode-free", "opencode-go")
_MERGE_PEER_FIELDS = (
    "weekly",
    "cursor_label",
    "cursor_period_end",
    "jobs",
    "repo",
    "sha",
    "started_at",
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
    # FR #5690: FX age + rate so tray can show freshness; server can unify GBP.
    "overage_fetched_at",
    "usd_gbp_rate",
    # FR #6147: OpenCode Go rolling/weekly/monthly window records for digest paint.
    "opencode_windows",
    # xAI weekly meter identity. remaining stays on weekly / pcent.grok-build.
    # The object is the peer-visible row: provider, direction, source, fetched_at, period_end.
    "xai_weekly_used_pct",
    "xai_weekly_source",
    "xai_weekly_fetched_at",
    "xai_weekly",
)
# FR #5690: when a merge payload carries these as null (or lists them in cleared[]),
# pop the sticky chair value. Omit-null used to leave stale overage/repo forever.
_CLEARABLE_MERGE_FIELDS = frozenset({
    "repo",
    "sha",
    "started_at",
    "working_on",
    "overage_gbp",
    "overage_usd",
    "overspend_state",
    "on_demand_used_cents",
    "on_demand_limit_cents",
    "on_demand_remaining_pct",
    "overage_fetched_at",
    "usd_gbp_rate",
    # FR #6144: omit/unknown Cursor must clear sticky label (not leave foreign 0%).
    "cursor_label",
    "xai_weekly_used_pct",
    "xai_weekly_source",
    "xai_weekly_fetched_at",
})
# FR #6144 / MRB #6169: one Cursor-group key set for clear / merge-skip / peer-block.
_CURSOR_GROUP_KEYS = frozenset({
    "pcent",
    "cursor_label",
    "cursor_pools",
    "sand_period_end",
    "cursor_period_end",
    "overage_gbp",
    "overage_usd",
    "overspend_state",
    "on_demand_used_cents",
    "on_demand_limit_cents",
    "on_demand_remaining_pct",
    "overage_fetched_at",
    "usd_gbp_rate",
    "remaining_pct",
    "account_remaining_pct",
    "cursor_remaining_pct",
    "cur",
})
_CURSOR_UNKNOWN_CLEAR_FIELDS = tuple(sorted(_CURSOR_GROUP_KEYS))
_PEER_CLEAR = object()  # sentinel: peer wants an explicit null clear in the merge delta
# FR #6143 / #6301: ear-owned identity scalars. Keep out of _MERGE_PEER_FIELDS so tray
# peer rewrites cannot clear or restore a stale label via peer fill.
_EAR_IDENTITY_FIELDS = ("grok_account", "opencode_account")
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
    "started_at",
    "overage_fetched_at",
    "usd_gbp_rate",
    "console_nicks",
    "cursor_known",
    "weekly_known",
    "grok_account",
    "opencode_account",
    "opencode_windows",
    "xai_weekly_used_pct",
    "xai_weekly_source",
    "xai_weekly_fetched_at",
    "xai_weekly",
)
WORKER_NICK_RE = re.compile(r"^w-([a-z0-9]+)-(\d+)_?$", re.I)

HELP_TEXT = (
    "GET https://bob.ntsa.uk/bob/v1/report   fleet JSON digest\n"
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


# FR #6143: Grok account label from auth.json (profile fields only; never key/refresh_token).
_GROK_ACCOUNT_MAX_LEN = 254
_GROK_API_KEY_SCOPE_RX = re.compile(r"(?i)(^|::)api[_-]?key$|xai::api_key")
_GROK_CTRL_RX = re.compile(r"[\x00-\x1f\x7f]")


def resolve_grok_auth_path(env: dict[str, str] | None = None) -> Path | None:
    """Path order: BOB_GROK_AUTH_PATH, nonempty GROK_AUTH_PATH, $GROK_HOME/auth.json, ~/.grok/auth.json."""
    e = os.environ if env is None else env
    for key in ("BOB_GROK_AUTH_PATH", "GROK_AUTH_PATH"):
        raw = (e.get(key) or "").strip()
        if raw:
            return Path(raw)
    grok_home = (e.get("GROK_HOME") or "").strip()
    if grok_home:
        return Path(grok_home) / "auth.json"
    return Path.home() / ".grok" / "auth.json"


def _sanitize_grok_account_label(raw: object) -> str | None:
    """Trim, strip controls, length-cap; reject secret-marker hits. Never log the value."""
    if not isinstance(raw, str):
        return None
    s = _GROK_CTRL_RX.sub("", raw).strip()
    if not s or len(s) > _GROK_ACCOUNT_MAX_LEN:
        return None
    if secret_marker_hit(s) or looks_like_secret(s):
        return None
    return s


def _label_from_grok_profile(obj: dict) -> str | None:
    """Prefer email; else first_name last_name. Read only those three keys."""
    email = _sanitize_grok_account_label(obj.get("email"))
    if email:
        return email
    first = _sanitize_grok_account_label(obj.get("first_name")) or ""
    last = _sanitize_grok_account_label(obj.get("last_name")) or ""
    name = " ".join(p for p in (first, last) if p).strip()
    return _sanitize_grok_account_label(name) if name else None


def _iter_grok_auth_profiles(doc: object) -> list[dict]:
    """Collect profile-bearing dicts from auth.json (issuer::client map or scopes)."""
    out: list[dict] = []
    if not isinstance(doc, dict):
        return out
    scopes = doc.get("scopes")
    items: list[tuple[object, object]] = []
    if isinstance(scopes, dict):
        items.extend(scopes.items())
    elif isinstance(scopes, list):
        for i, row in enumerate(scopes):
            items.append((i, row))
    # Live ~/.grok/auth.json is keyed by issuer::client_id at the top level.
    if not items:
        items = list(doc.items())
    for key, val in items:
        key_s = str(key or "")
        if _GROK_API_KEY_SCOPE_RX.search(key_s):
            continue
        if not isinstance(val, dict):
            continue
        # Skip credential-only blobs with no profile fields.
        if not any(k in val for k in ("email", "first_name", "last_name")):
            continue
        out.append(val)
    return out


def read_grok_account_label(env: dict[str, str] | None = None) -> tuple[str, str | None]:
    """FR #6143: tri-state Grok account label from auth.json.

    Returns ``(\"ok\", label)``, ``(\"none\", None)``, or ``(\"unknown\", None)``.
    Never returns key / refresh_token / other credential fields.
    """
    path = resolve_grok_auth_path(env)
    if path is None:
        return ("none", None)
    try:
        if not path.is_file():
            return ("none", None)
        raw = path.read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ("unknown", None)
    if not isinstance(doc, dict):
        return ("none", None)
    labels: list[str] = []
    seen: set[str] = set()
    for profile in _iter_grok_auth_profiles(doc):
        label = _label_from_grok_profile(profile)
        if not label:
            continue
        if label not in seen:
            seen.add(label)
            labels.append(label)
    if not labels:
        return ("none", None)
    if len(labels) > 1:
        return ("none", None)
    return ("ok", labels[0])


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
    """Jeeves: every ChanServ-registered channel (FR #3836).

    Prefer the persisted full ``channels`` list from the ChanServ LIST mirror (shops,
    #bobiverse, #wonderland, other registered names). Fall back to #bobiverse +
    #wonderland + shops when the registry has no ``channels`` field yet (FR #3834).
    Never invent unregistered channels.
    """
    if home is None:
        env_home = (os.environ.get("BOB_DIGEST_HOME") or "").strip()
        home = Path(env_home) if env_home else None
        if home is None:
            chair = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
            if chair:
                # Prefer digest home sibling used by Start-Jeeves
                cand = Path(chair) / ".bobiverse"
                home = cand if cand.is_dir() else None
    if home is not None:
        chans = registered_machines.load_registered_channels(Path(home))
        if chans:
            return chans
    shops = [shop_channel(mid) for mid in roster_machine_ids(home, fold=False)]   # still joins legacy #ionos
    return [FLEET_CHANNEL, WONDERLAND_CHANNEL] + shops


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
    """bob-* -> fleet + wonderland + shop; talk seats / w-* -> own #{machine} only.

    First JOIN creates #{machine} on Ergo. CAST IRON (Simon 2026-09-25): worker
    processes - talk seats ({machine}-{pid}) and w-* - JOIN their own #{machine}
    ONLY, never #bobiverse, #wonderland, or extras (#agentic_irc). Only bob-{machine},
    Jeeves and humans belong in #bobiverse / #wonderland. FR #3834 adds #wonderland
    for Bob ears (airc client fallback + ear +o). Supersedes issue #108 / PR #107.
    """
    req = parse_channel_list(requested)
    worker = parse_worker_nick(nick)
    if worker:
        return [shop_channel(worker[0])]
    mid = machine_from_nick(nick)
    if mid:
        shop = shop_channel(mid)
        return [FLEET_CHANNEL, WONDERLAND_CHANNEL, shop]
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
    raw = (os.environ.get(DIGEST_URL_ENV) or os.environ.get("BOB_DIGEST_URL") or "").strip()
    if raw:
        return raw
    try:
        import bob_public_base as _bpb
        return _bpb.default_digest_url()
    except ImportError:  # pragma: no cover
        return DEFAULT_DIGEST_URL


def fetch_digest_http(url: str | None = None, timeout: float = 15.0) -> dict | None:
    """GET public digest JSON. Returns None on any failure."""
    import urllib.error
    import urllib.request

    target = (url or digest_url()).strip()
    if not target:
        return None
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": DIGEST_HTTP_USER_AGENT,
            },
        )
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
        "console_nicks": [],
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
    # FR #4211: keep heartbeat so live_seat_nicks can skip stale legacy workers.
    updated = str(ent.get("updated") or ent.get("last_seen") or ent.get("lastSeen") or "").strip()
    if updated:
        out["updated"] = updated
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


def _sync_running_queued_from_jobs(ent: dict) -> None:
    """FR #5687: derive machines.<id>.running/queued from the jobs list.

    Empty jobs must yield running=0 and queued=0 so export never contradicts
    itself after FR #663 clears jobs when no worker_list row is doing.
    """
    jobs = ent.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    running = 0
    queued = 0
    for item in jobs:
        if not isinstance(item, dict):
            continue
        st = str(item.get("state") or "running").strip().lower() or "running"
        if st in ("queued", "pending", "waiting", "queue"):
            queued += 1
        else:
            running += 1
    ent["running"] = running
    ent["queued"] = queued


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
        # FR #5698 / #5704 / #5724: idle export must not keep sticky repo/sha
        # (peer false-publish left marchhare repo=hrsmith after jobs=[]).
        for key in ("repo", "sha", "started_at"):
            ent[key] = ""
    # FR #5687: keep running/queued aligned with (possibly cleared) jobs.
    _sync_running_queued_from_jobs(ent)


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


def coerce_console_nicks(raw: object) -> list[str]:
    """FR #5204: public ``*_console`` nicks only (no secrets, no workers)."""
    if not isinstance(raw, (list, tuple, set)):
        return []
    out = []
    seen = set()
    for item in raw:
        nick = str(item or "").strip()
        low = nick.lower()
        if not nick or not low.endswith("_console") or low in seen:
            continue
        seen.add(low)
        out.append(nick)
    return sorted(out, key=lambda s: s.lower())


def console_nicks_from_present(present: object) -> list[str]:
    """NAMES / JOIN set -> credential-free airc console nicks."""
    return coerce_console_nicks(present)


def normalize_irc_channel(channel: str) -> str:
    ch = str(channel or "").strip()
    if not ch:
        return ""
    if not ch.startswith("#"):
        ch = "#" + ch
    return ch.lower()


def machine_hint_for_console(nick: str, channel: str, shop_mid: str | None = None) -> str:
    """FR #5947: shop mid when known; else nick stem before _console; else channel id."""
    if shop_mid:
        return fold_machine_id(normalize_machine_id(shop_mid) or shop_mid)
    low = str(nick or "").strip().lower()
    if low.endswith("_console") and len(low) > len("_console"):
        stem = low[: -len("_console")]
        return fold_machine_id(normalize_machine_id(stem) or stem)
    ch = normalize_irc_channel(channel)
    if ch.startswith("#") and len(ch) > 1:
        mid = normalize_machine_id(ch[1:]) or ch[1:]
        return fold_machine_id(mid) if mid else ""
    return ""


def coerce_airc_console_presence(raw: object) -> list[dict]:
    """FR #5947: [{nick, channel, machine}] credential-free presence rows."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in raw:
        if isinstance(item, str):
            nick = item.strip()
            channel = ""
            machine = machine_hint_for_console(nick, "")
        elif isinstance(item, dict):
            nick = str(item.get("nick") or "").strip()
            channel = normalize_irc_channel(str(item.get("channel") or ""))
            machine = str(item.get("machine") or "").strip()
            if not machine:
                machine = machine_hint_for_console(nick, channel)
            else:
                machine = fold_machine_id(normalize_machine_id(machine) or machine)
        else:
            continue
        low = nick.lower()
        if not nick or not low.endswith("_console"):
            continue
        key = (low, channel.lower())
        if key in seen:
            continue
        seen.add(key)
        row = {"nick": nick, "channel": channel, "machine": machine}
        out.append(row)
    out.sort(key=lambda r: (str(r.get("nick") or "").lower(), str(r.get("channel") or "").lower()))
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
            "worker_list": _coerce_worker_list(raw.get("worker_list")),
            "console_nicks": coerce_console_nicks(raw.get("console_nicks")),
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
    for flag in ("cursor_known", "weekly_known"):
        if flag in raw and raw[flag] is not None:
            base[flag] = bool(raw[flag])
    # FR #6143: ear-owned identity survives reload; never peer-filled.
    for key in _EAR_IDENTITY_FIELDS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            cleaned = _sanitize_grok_account_label(val)
            if cleaned:
                base[key] = cleaned
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

            # SYNCHRONIZE - OpenProcess succeeds for live PIDs we can see; ACCESS_DENIED (5) often
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
        # Never unlink a lock still held by *this* live process - health-watchdog
        # GET timeouts used to break our own 30s+ holder (mtime not refreshed) and
        # cascade ConnectionAbortedError + foreign-stale fights with the chair.
        # FR #6100: exception when digest *content* ts is also stale (hung writer).
        if own_live:
            reason = None
            content_limit = digest_stale_s()
            if age >= content_limit:
                try:
                    doc = json.loads(digest_path(Path(home)).read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    doc = None
                if digest_is_stale(doc if isinstance(doc, dict) else None):
                    reason = "hung-own-content-stale"
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


@_digest_locked
def set_machine_console_nicks(home: Path, mid: str, nicks: object) -> list[str]:
    """Persist shop ``*_console`` presence for GET /bob/v1/report."""
    cid = fold_machine_id(normalize_machine_id(mid) or mid)
    cleaned = coerce_console_nicks(nicks)
    doc = load_digest(home)
    machines = doc.setdefault("machines", {})
    if not isinstance(machines, dict):
        machines = {}
        doc["machines"] = machines
    ent = machines.get(cid)
    if not isinstance(ent, dict):
        ent = _empty_machine(cid)
        machines[cid] = ent
    if coerce_console_nicks(ent.get("console_nicks")) != cleaned:
        ent["console_nicks"] = cleaned
        save_digest(home, doc)
    return cleaned


@_digest_locked
def remove_machine_console_nick(home: Path, mid: str, nick: str) -> list[str]:
    cid = fold_machine_id(normalize_machine_id(mid) or mid)
    gone = str(nick or "").strip().lower()
    doc = load_digest(home)
    ent = (doc.get("machines") or {}).get(cid)
    if not isinstance(ent, dict):
        return []
    kept = [n for n in coerce_console_nicks(ent.get("console_nicks")) if n.lower() != gone]
    if kept != coerce_console_nicks(ent.get("console_nicks")):
        ent["console_nicks"] = kept
        save_digest(home, doc)
    return kept


@_digest_locked
def set_channel_console_presence(
    home: Path,
    channel: str,
    nicks: object,
    *,
    machine: str | None = None,
) -> list[dict]:
    """FR #5947: replace *_console presence rows for one IRC channel (any chair channel)."""
    ch = normalize_irc_channel(channel)
    if not ch:
        return coerce_airc_console_presence(load_digest(home).get("airc_console_presence"))
    cleaned = coerce_console_nicks(nicks)
    doc = load_digest(home)
    rows = [
        r
        for r in coerce_airc_console_presence(doc.get("airc_console_presence"))
        if str(r.get("channel") or "").lower() != ch
    ]
    for nick in cleaned:
        rows.append(
            {
                "nick": nick,
                "channel": ch,
                "machine": machine_hint_for_console(nick, ch, machine),
            }
        )
    rows = coerce_airc_console_presence(rows)
    prev = coerce_airc_console_presence(doc.get("airc_console_presence"))
    if rows != prev:
        doc["airc_console_presence"] = rows
        save_digest(home, doc)
    return rows


@_digest_locked
def remove_channel_console_nick(home: Path, nick: str, channel: str | None = None) -> list[dict]:
    """Drop one console from a channel (PART/KICK), or from every channel when channel is None (QUIT)."""
    gone = str(nick or "").strip().lower()
    ch = normalize_irc_channel(channel) if channel else ""
    doc = load_digest(home)
    prev = coerce_airc_console_presence(doc.get("airc_console_presence"))
    kept = []
    for r in prev:
        if str(r.get("nick") or "").lower() != gone:
            kept.append(r)
            continue
        if ch and str(r.get("channel") or "").lower() != ch:
            kept.append(r)
    kept = coerce_airc_console_presence(kept)
    if kept != prev:
        doc["airc_console_presence"] = kept
        save_digest(home, doc)
    return kept


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
    if "cursor_known" in ent:
        view["cursor_known"] = ent.get("cursor_known")
    if "weekly_known" in ent:
        view["weekly_known"] = ent.get("weekly_known")
    # FR #6143: label-only change must fingerprint so merge returns 204.
    for key in _EAR_IDENTITY_FIELDS:
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
            # FR #6144: Sand reset stays on sand_period_end (never xAI period_end).
            if pid in ("grok-weekly", "grok-chat"):
                field = "sand_period_end"
            else:
                field = "cursor_period_end"
            if ent.get(field) in (None, ""):
                ent[field] = pe
    if changed and not ent.get("_skip_pool_pcent_backfill"):
        ent["pcent"] = pcent


def _clearable_empty(val: object) -> bool:
    """True when a clearable merge value means 'unknown / gone' (null or blank string)."""
    return val is None or val == ""


def _usd_gbp_rate_from_env_or_payload(payload: dict) -> float | None:
    """Prefer env BOB_CURSOR_USD_GBP_RATE (chair-wide), else payload usd_gbp_rate."""
    rate_env = (os.environ.get("BOB_CURSOR_USD_GBP_RATE") or "").strip()
    if rate_env:
        try:
            rate = float(rate_env)
            if rate > 0:
                return rate
        except (TypeError, ValueError):
            pass
    raw = payload.get("usd_gbp_rate")
    if raw is None or raw == "":
        return None
    try:
        rate = float(raw)
    except (TypeError, ValueError):
        return None
    return rate if rate > 0 else None


def _unify_overage_gbp_from_usd(ent: dict, payload: dict) -> None:
    """FR #5690: one shared USD->GBP conversion so peers do not disagree on FX.

    When overage_usd is present, recompute overage_gbp from a single rate and stamp
    usd_gbp_rate + overage_fetched_at on the machine row.
    """
    usd_raw = ent.get("overage_usd")
    if usd_raw in (None, ""):
        return
    try:
        usd = float(usd_raw)
    except (TypeError, ValueError):
        return
    rate = _usd_gbp_rate_from_env_or_payload(payload)
    if rate is None and ent.get("usd_gbp_rate") not in (None, ""):
        try:
            rate = float(ent.get("usd_gbp_rate"))
        except (TypeError, ValueError):
            rate = None
    if rate is None or rate <= 0:
        return
    ent["overage_gbp"] = round(usd * rate, 2)
    ent["usd_gbp_rate"] = rate
    fetched = payload.get("overage_fetched_at")
    if fetched not in (None, ""):
        ent["overage_fetched_at"] = str(fetched)
    elif ent.get("overage_fetched_at") in (None, ""):
        ent["overage_fetched_at"] = _utc_now_iso()


def _apply_cleared_merge_fields(ent: dict, payload: dict) -> None:
    """FR #5690: honor cleared[] and explicit nulls for sticky clearable fields."""
    cleared = payload.get("cleared")
    keys: list[str] = []
    if isinstance(cleared, list):
        for item in cleared:
            k = str(item or "").strip()
            if k:
                keys.append(k)
    for key in _CLEARABLE_MERGE_FIELDS:
        if key in payload and _clearable_empty(payload.get(key)):
            keys.append(key)
    # FR #6143: grok_account clears via null / "" / cleared[] (ear-owned, not peer).
    for key in _EAR_IDENTITY_FIELDS:
        if key in payload and _clearable_empty(payload.get(key)):
            keys.append(key)
    for key in keys:
        if key in _EAR_IDENTITY_FIELDS:
            ent.pop(key, None)
            continue
        if key not in _CLEARABLE_MERGE_FIELDS and key != "working_on":
            continue
        if key == "working_on":
            # Machine-level blank: roll from workers rather than inventing activity.
            ent["working_on"] = ""
            _roll_working_on(ent)
            continue
        ent.pop(key, None)


def _non_cursor_pcent(pcent: object) -> dict:
    """xAI weekly and OpenCode percents. Not Cursor Sand / grok-chat."""
    if not isinstance(pcent, dict):
        return {}
    out: dict = {}
    for key in _NON_CURSOR_PCENT_KEYS:
        if key not in pcent or pcent.get(key) in (None, ""):
            continue
        out[key] = pcent.get(key)
    return out


def _merge_non_cursor_pcent(existing: object, incoming: object | None) -> dict:
    """Keep grok-build and OpenCode when cursor_known is false.

    Cursor keys in either map are dropped. An incoming null for a kept key clears it.
    ``incoming is None`` means the payload omitted pcent: keep the existing non-Cursor keys.
    """
    kept = _non_cursor_pcent(existing)
    if not isinstance(incoming, dict):
        return kept
    for key in _NON_CURSOR_PCENT_KEYS:
        if key not in incoming:
            continue
        if incoming.get(key) in (None, ""):
            kept.pop(key, None)
        else:
            kept[key] = incoming.get(key)
    return kept


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
    # FR #976: reporter says weekly is unknown - clear a stuck 0 (lesser ratchet left 0 forever).
    weekly_known = payload.get("weekly_known")
    if "weekly_known" in payload and _is_false_like(weekly_known):
        ent.pop("weekly", None)
    # FR #6144: cursor_known=false clears Cursor group; omit keeps legacy merge.
    cursor_known_raw = payload.get("cursor_known") if "cursor_known" in payload else None
    cursor_unknown = False
    if "cursor_known" in payload:
        if _is_false_like(cursor_known_raw):
            cursor_unknown = True
            ent["cursor_known"] = False
            for ck in _CURSOR_UNKNOWN_CLEAR_FIELDS:
                if ck == "pcent":
                    continue
                ent.pop(ck, None)
            ent["pcent"] = _merge_non_cursor_pcent(
                ent.get("pcent"), payload.get("pcent") if "pcent" in payload else None
            )
            if not ent["pcent"]:
                ent.pop("pcent", None)
        else:
            ent["cursor_known"] = True
    if (not cursor_unknown) and "pcent" in payload and isinstance(payload["pcent"], dict):
        # FR #976: per-machine pcent is replace-latest (reporter's current reading), not min-ratchet.
        ent["pcent"] = _merge_pcent_lesser(
            ent.get("pcent"), payload["pcent"], replace=True
        )
    if payload.get("uptime_since"):
        ent["uptime_since"] = str(payload["uptime_since"])
    if (not cursor_unknown) and isinstance(payload.get("cursor_pools"), list):
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
    # FR #5690: apply clears before writes so sticky overage/repo cannot linger.
    _apply_cleared_merge_fields(ent, payload)
    for key in _MERGE_PEER_FIELDS:
        if key not in payload:
            continue
        val = payload[key]
        # Explicit null / blank for clearable keys already popped above.
        if _clearable_empty(val) and key in _CLEARABLE_MERGE_FIELDS:
            continue
        if val is None:
            continue
        if key == "jobs" and not isinstance(val, list):
            continue
        if key == "pcent" and isinstance(val, dict):
            continue
        if cursor_unknown and key in _CURSOR_GROUP_KEYS:
            continue
        if key in ("weekly",) and val is not None:
            # FR #976: skip write when reporter marked weekly unknown (cleared above).
            if "weekly_known" in payload and _is_false_like(weekly_known):
                continue
            # Per-machine weekly is replace-latest (not min-ratchet).
            ent[key] = val
            continue
        ent[key] = val
    # FR #6143: ear-owned grok_account (omit = keep; null/blank already cleared above).
    for key in _EAR_IDENTITY_FIELDS:
        if key not in payload:
            continue
        val = payload[key]
        if _clearable_empty(val):
            continue
        cleaned = _sanitize_grok_account_label(val)
        if cleaned:
            ent[key] = cleaned
    # FR #5690: unify GBP from USD with one rate after field writes.
    if "overage_usd" in payload and not _clearable_empty(payload.get("overage_usd")):
        _unify_overage_gbp_from_usd(ent, payload)
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
    digest still shows ``doing bobiverse MRB #N`` - that false busy made every
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
    action = f"lost {nick} - {shop} closed"
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
    elif ev == "issue_comment":
        # FR #4711: owner comments may clear needs_human; announce lightly.
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
                bits.append(title[:80])
    elif ev in ("check_run", "check_suite"):
        # FR #4706: surface completed failures so the chair log shows re-queue drivers.
        blob = payload.get("check_run") if ev == "check_run" else payload.get("check_suite")
        if isinstance(blob, dict):
            action = str(payload.get("action") or "").strip()
            if action:
                bits.append(action)
            conclusion = str(blob.get("conclusion") or "").strip()
            if conclusion:
                bits.append(conclusion)
            name = str(blob.get("name") or "").strip()
            if name:
                bits.append(name[:80])
            prs = blob.get("pull_requests")
            if isinstance(prs, list) and prs:
                nums = []
                for p in prs[:3]:
                    if isinstance(p, dict) and p.get("number") is not None:
                        nums.append(f"#{p.get('number')}")
                if nums:
                    bits.append(",".join(nums))
            head = str(blob.get("head_sha") or "").strip()
            if head:
                bits.append(head[:12])
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
    """Announce path only - never secret-scan the full GitHub JSON body (FR #206).

    FR #4706: ``check_run`` / ``check_suite`` also drive merge-on-green FIX re-offers
    for parked CI-failed tips (new head SHA) without waiting for ``!resync``.
    Successful check noise is stamped but not announced on #bobiverse.
    """
    if not (event or "").strip():
        return GitWebhookOutcome(ok=False, err="no event")
    if not isinstance(payload, dict):
        return GitWebhookOutcome(ok=False, err="malformed")
    import gitclaim
    import github_api_budget as gab

    ev = (event or "").strip().lower()
    if ev == "check_run":
        try:
            import mrb_merge_on_green

            mrb_merge_on_green.handle_check_run_event(home, payload)
        except Exception:  # noqa: BLE001
            pass
        gab.stamp_git_webhook(home)
        cr = payload.get("check_run") if isinstance(payload.get("check_run"), dict) else {}
        conclusion = str((cr or {}).get("conclusion") or "").strip().lower()
        status = str((cr or {}).get("status") or "").strip().lower()
        fail_like = conclusion in (
            "failure",
            "timed_out",
            "action_required",
            "cancelled",
            "canceled",
        )
        if status == "completed" and fail_like:
            line = format_github_webhook_announce(event, payload)
            if not line.startswith(GIT_ANNOUNCE_PREFIX):
                return GitWebhookOutcome(ok=False, err="announce")
            hit = secret_marker_hit(line)
            if hit:
                line = redact_git_announce_line(line, hit)
            if not enqueue_chair_fleet_privmsg(home, line):
                return GitWebhookOutcome(ok=False, err="outbox")
            return GitWebhookOutcome(ok=True, announced=True)
        return GitWebhookOutcome(ok=True, announced=False)
    if ev == "check_suite":
        # Accept + stamp; FIX re-offer is driven by per-run check_run events.
        gab.stamp_git_webhook(home)
        suite = payload.get("check_suite") if isinstance(payload.get("check_suite"), dict) else {}
        conclusion = str((suite or {}).get("conclusion") or "").strip().lower()
        status = str((suite or {}).get("status") or "").strip().lower()
        fail_like = conclusion in (
            "failure",
            "timed_out",
            "action_required",
            "cancelled",
            "canceled",
        )
        if status == "completed" and fail_like:
            line = format_github_webhook_announce(event, payload)
            if line.startswith(GIT_ANNOUNCE_PREFIX):
                hit = secret_marker_hit(line)
                if hit:
                    line = redact_git_announce_line(line, hit)
                enqueue_chair_fleet_privmsg(home, line)
                return GitWebhookOutcome(ok=True, announced=True)
        return GitWebhookOutcome(ok=True, announced=False)

    # FR #4711: owner issue_comment after giveup_ts clears needs_human before announce.
    if ev == "issue_comment":
        try:
            gitclaim.clear_needs_human_from_owner_issue_comment(home, event, payload)
        except Exception:  # noqa: BLE001
            pass
        try:
            import copilot_dispatch

            copilot_dispatch.handle_issue_comment(home, payload)
        except Exception:  # noqa: BLE001
            pass
    try:
        import copilot_dispatch as _cd5170

        _cd5170.stamp_webhook_activity(home, ev, payload)
    except Exception:  # noqa: BLE001
        pass

    line = format_github_webhook_announce(event, payload)
    if not line.startswith(GIT_ANNOUNCE_PREFIX):
        return GitWebhookOutcome(ok=False, err="announce")
    hit = secret_marker_hit(line)
    if hit:
        line = redact_git_announce_line(line, hit)

    claim = gitclaim.claim_from_payload(event, payload, line=line)
    if claim is not None:
        queued = gitclaim.enqueue_unaccepted(home, claim)
        # FR #1811: surface queue-lock-timeout / queue-read / queue-write (claim also spooled).
        if isinstance(queued, str) and queued.startswith("error"):
            err = queued.split(":", 1)[1] if ":" in queued else "queue"
            return GitWebhookOutcome(ok=False, err=err or "queue")
        # FR #4827: tell the duplicate seat to stand down in its shop.
        for note in gitclaim.drain_stand_down(home):
            text = str(note.get("text") or "").strip()
            chan = str(note.get("channel") or "").strip()
            if text and chan:
                enqueue_chair_fleet_privmsg(home, text, channel=chan)
    # FR #4959: drop list ETags for this repo so the next reconcile re-GETs issues/pulls
    # even when webhook enqueue missed a lesson (or other) MRB row.
    if ev in ("pull_request", "issues"):
        repo_name = ""
        try:
            repo_name = _github_repo_name(payload)
        except Exception:  # noqa: BLE001
            repo_name = ""
        if repo_name:
            homes = {Path(home), fleet_digest_home(Path(home))}
            try:
                import bob_home

                homes.add(Path(bob_home.chair_home()))
                homes.add(Path(bob_home.digest_home()))
            except Exception:  # noqa: BLE001
                pass
            for h in homes:
                with contextlib.suppress(Exception):
                    gab.invalidate_repo_list_etags(h, repo_name)
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
        # Explicit bob-* that is not the canonical mid nick is a legacy alias - ignore.
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
    # FR #6144: do not peer-refill Cursor group when cursor_known is false, or weekly when unknown.
    cursor_known_ent = ent.get("cursor_known")
    weekly_known_ent = ent.get("weekly_known")
    _cursor_peer_block = set(_CURSOR_GROUP_KEYS)
    peer = bobstat.read_peer(home, mid)
    if peer:
        for key in _peer_fill_keys():
            if key not in peer or peer[key] is None or peer[key] == "":
                continue
            if cursor_known_ent is False and key in _cursor_peer_block:
                continue
            if weekly_known_ent is False and key == "weekly":
                continue
            if key not in base or base.get(key) in (None, "", [], {}):
                base[key] = peer[key]
    for key in _peer_fill_keys():
        if key in ent and ent[key] is not None and ent[key] != "":
            base[key] = ent[key]
    if cursor_known_ent is False and peer:
        kept = _non_cursor_pcent(base.get("pcent"))
        for key, val in _non_cursor_pcent(peer.get("pcent")).items():
            kept.setdefault(key, val)
        if kept:
            base["pcent"] = kept
    if cursor_known_ent is False:
        for key in _cursor_peer_block:
            if key == "pcent":
                kept = _non_cursor_pcent(base.get("pcent"))
                if kept:
                    base["pcent"] = kept
                else:
                    base.pop("pcent", None)
                continue
            base.pop(key, None)
        base["cursor_known"] = False
    if "cursor_known" in ent:
        base["cursor_known"] = ent.get("cursor_known")
    if "weekly_known" in ent:
        base["weekly_known"] = ent.get("weekly_known")
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
    out["console_nicks"] = coerce_console_nicks(base.get("console_nicks"))
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
    """Per-pool reset clock (FR #6144): dedicated Sand/billing first, then this machine's
    stored pool-row period_end, then legacy machine ``period_end`` only when no Cursor
    clocks or pool rows exist. grok-weekly/sand never uses xAI ``period_end`` when Sand
    clock is present (#80)."""
    pid = str(pool_id or "").strip().lower()
    rows = ent.get("cursor_pools") if isinstance(ent.get("cursor_pools"), list) else []
    row_pe = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("id") or row.get("group_id") or "").strip().lower()
        if pid in ("grok-weekly", "grok-chat", "sand", "cursor-grok-chat"):
            if rid not in ("grok-weekly", "grok-chat", "sand", "cursor-grok-chat"):
                continue
        else:
            aliases = {pid, "auto", "low-cost-models", "cursor-models", "high-cost-models"}
            if rid not in aliases and rid != pid:
                continue
        pe = row.get("period_end") or row.get("reset")
        if pe not in (None, ""):
            row_pe = str(pe)
            break
    has_cursor_clock = any(
        ent.get(k) not in (None, "") for k in ("sand_period_end", "cursor_period_end")
    ) or bool(rows)
    if pid in ("grok-weekly", "grok-chat", "sand", "cursor-grok-chat"):
        weekly = ent.get("sand_period_end")
        if weekly not in (None, ""):
            period_s = str(weekly)
            return period_s, period_s
        if row_pe:
            return row_pe, row_pe
        # FR #6144: legacy period_end was the Sand/weekly clock before sand_period_end
        # existed. Prefer it for grok pools when Sand clock is absent (even if
        # cursor_period_end is set). Never prefer period_end over sand_period_end.
        legacy = ent.get("period_end")
        if legacy not in (None, ""):
            period_s = str(legacy)
            return period_s, period_s
        return None, None
    cursor_period = ent.get("cursor_period_end")
    if cursor_period not in (None, ""):
        period_s = str(cursor_period)
        return period_s, period_s
    if row_pe:
        return row_pe, row_pe
    if not has_cursor_clock:
        weekly = ent.get("period_end")
        if weekly not in (None, ""):
            period_s = str(weekly)
            return period_s, period_s
    return None, None


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
DEFAULT_DIGEST_STALE_S = 900.0      # FR #6100: public digest ts / lastSeen older than this is stale


def digest_stale_s() -> float:
    raw = (os.environ.get("BOB_DIGEST_STALE_S") or "").strip()
    if not raw:
        return DEFAULT_DIGEST_STALE_S
    try:
        return max(30.0, float(raw))
    except ValueError:
        return DEFAULT_DIGEST_STALE_S


def digest_clock_ts(doc: dict | None) -> datetime | None:
    """Newest usable clock in the digest: top-level ts, else max machine lastSeen."""
    if not isinstance(doc, dict):
        return None
    top = _parse_iso_ts(doc.get("ts") or doc.get("updated"))
    seen: list[datetime] = []
    machines = doc.get("machines") if isinstance(doc.get("machines"), dict) else {}
    for ent in machines.values():
        if not isinstance(ent, dict):
            continue
        parsed = _parse_iso_ts(ent.get("lastSeen") or ent.get("updated"))
        if parsed is not None:
            seen.append(parsed)
    if top is not None:
        return top
    if seen:
        return max(seen)
    return None


def digest_age_s(doc: dict | None, now: datetime | None = None) -> float | None:
    clock = digest_clock_ts(doc)
    if clock is None:
        return None
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0.0, (ref - clock).total_seconds())


def digest_is_stale(doc: dict | None, now: datetime | None = None) -> bool:
    age = digest_age_s(doc, now)
    if age is None:
        return False
    return age > digest_stale_s()


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


def _digest_copilot_pool(home: Path) -> dict:
    try:
        import copilot_dispatch

        return copilot_dispatch.pool_for_digest(home)
    except Exception:  # noqa: BLE001
        return {"state": "unknown", "source": "copilot_internal/user"}


def _intake_outbox_public(home: Path) -> dict:
    """FR #5359: queued intake/outbox count + age + gh presence (no secrets)."""
    try:
        import intake

        snap = intake.intake_outbox_snapshot(home)
    except Exception:
        snap = {"count": 0, "oldest_age_s": None, "gh_cli": False}
    return {
        "count": int(snap.get("count") or 0),
        "oldest_age_s": snap.get("oldest_age_s"),
        "gh_cli": bool(snap.get("gh_cli")),
    }



def _digest_stuck(home: Path) -> list:
    try:
        import stuck_job_sweep
        return stuck_job_sweep.digest_stuck_section(home)
    except Exception:
        return []


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
    age_s = digest_age_s(doc, now)
    stale = digest_is_stale(doc, now)
    return {
        "v": int(doc.get("v") or 1),
        "ts": str(doc.get("ts") or _utc_now_iso()),
        "stale": stale,
        "stale_age_s": None if age_s is None else int(age_s),
        "airc_consoles_stale": stale,
        "briefer": briefer,
        "chairNick": chair or briefer,
        "machines": exported,
        "roster_machine_ids": sorted(roster),
        "chair_channels": channels,
        "cursor_pools": build_cursor_pools(doc, exported, now),
        "queue": _public_queue(home),
        "copilot": _digest_copilot_pool(home),
        "intake_outbox": _intake_outbox_public(home),
        # FR #5204 / #5947: live airc *_console nicks (shops + any chair channel).
        "airc_consoles": _airc_consoles_export(doc, exported),
        "airc_console_details": _airc_console_details_export(doc, exported),
        # FR #5510: stuck-job sweep report (silent accepts / untracked / held rules).
        "stuck": _digest_stuck(home),
    }


def _airc_consoles_from_machines(machines: dict) -> list[str]:
    found: list[str] = []
    for ent in (machines or {}).values():
        if isinstance(ent, dict):
            found.extend(coerce_console_nicks(ent.get("console_nicks")))
    return coerce_console_nicks(found)


def _airc_consoles_from_presence(doc: dict) -> list[str]:
    return coerce_console_nicks(
        [r.get("nick") for r in coerce_airc_console_presence((doc or {}).get("airc_console_presence"))]
    )


def _airc_consoles_export(doc: dict, machines: dict) -> list[str]:
    found = _airc_consoles_from_machines(machines) + _airc_consoles_from_presence(doc)
    return coerce_console_nicks(found)


def _airc_console_details_export(doc: dict, machines: dict) -> list[dict]:
    """FR #5947: [{nick, machine, channel}] for picker / ops; no secrets."""
    rows = list(coerce_airc_console_presence((doc or {}).get("airc_console_presence")))
    seen = {(str(r.get("nick") or "").lower(), str(r.get("channel") or "").lower()) for r in rows}
    for mid, ent in (machines or {}).items():
        if not isinstance(ent, dict):
            continue
        shop = str(ent.get("shop") or shop_channel(mid) or "").strip()
        ch = normalize_irc_channel(shop) if shop else normalize_irc_channel("#" + str(mid))
        for nick in coerce_console_nicks(ent.get("console_nicks")):
            key = (nick.lower(), ch.lower())
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "nick": nick,
                    "channel": ch,
                    "machine": fold_machine_id(normalize_machine_id(mid) or mid),
                }
            )
    return coerce_airc_console_presence(rows)


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
        # FR #5690: peer cleared a sticky field the chair still holds -> send explicit null.
        if key in _CLEARABLE_MERGE_FIELDS and cv not in (None, ""):
            return _PEER_CLEAR
        return None
    if looks_like_secret(str(pv)):
        return None
    return pv


def _peer_delta_put(payload: dict, key: str, val: object) -> bool:
    """Apply a peer delta value; _PEER_CLEAR becomes JSON null. Returns True if payload changed."""
    if val is _PEER_CLEAR:
        payload[key] = None
        return True
    if val is not None:
        payload[key] = val
        return True
    return False



DIGEST_FUEL_HEARTBEAT_ENV = "BOB_EAR_DIGEST_FUEL_S"
DEFAULT_DIGEST_FUEL_HEARTBEAT_S = 30.0
# FR #6145: ear polls for fingerprint delta at this cadence (max lag pin).
DIGEST_FUEL_DELTA_ENV = "BOB_EAR_DIGEST_FUEL_DELTA_S"
DEFAULT_DIGEST_FUEL_DELTA_S = 5.0
DIGEST_FUEL_MAX_LAG_S = DEFAULT_DIGEST_FUEL_DELTA_S
_FALSE_LIKE_VALUES = (0, "false", "False", "0", "")


def _is_false_like(raw: object) -> bool:
    """Chair/ear agree: False or false-like scalars count as unknown/false."""
    return raw is False or raw in _FALSE_LIKE_VALUES


def _normalize_peer_cursor_known(peer: dict) -> bool | None:
    """Tri-state cursor_known from peer JSON for ear publish (FR #6188).

    True/False when the peer carries an explicit flag (bool or false-like scalar).
    None when the key is absent or the value is None --- omit on the wire so the
    chair keeps legacy merge for old peers. Do not infer from Cursor measurements.
    """
    if not isinstance(peer, dict) or "cursor_known" not in peer:
        return None
    raw = peer.get("cursor_known")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if _is_false_like(raw):
        return False
    return True


_FUEL_PUBLISH_EXTRA_FIELDS = (
    "weekly_known",
    "remaining_pct",
    "overage_fetched_at",
    "account_remaining_pct",
    "cursor_remaining_pct",
    "cursor_pools",
    "fuel_mode",
)


def digest_fuel_heartbeat_s() -> float:
    raw = (os.environ.get(DIGEST_FUEL_HEARTBEAT_ENV) or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_DIGEST_FUEL_HEARTBEAT_S


def digest_fuel_delta_s() -> float:
    """FR #6145: how often the ear may check for a fuel fingerprint delta (default 5s).

    Cap at DIGEST_FUEL_MAX_LAG_S so a large BOB_EAR_DIGEST_FUEL_DELTA_S cannot
    break the FR-005 five-second lag pin.
    """
    raw = (os.environ.get(DIGEST_FUEL_DELTA_ENV) or "").strip()
    if raw:
        try:
            return min(DIGEST_FUEL_MAX_LAG_S, max(0.0, float(raw)))
        except ValueError:
            pass
    return DEFAULT_DIGEST_FUEL_DELTA_S


def digest_fuel_post_state_path(home: Path) -> Path:
    return Path(home) / "digest-fuel-post-state.json"


def peer_fuel_fingerprint(peer: dict) -> str:
    """Stable fingerprint of fuel fields that must trigger a merge POST (FR #6141 / #6145).

    FR #6145: remaining / OpenCode pcent / Copilot overage_fetched_at / grok_account
    deltas must force a merge POST (no suppress).
    """
    if not isinstance(peer, dict):
        return ""
    parts: list[str] = []
    # FR #6188: normalised cursor_known so flag-only flips POST before heartbeat.
    parts.append(f"cursor_known={_normalize_peer_cursor_known(peer)!s}")
    for key in (
        "weekly",
        "weekly_known",
        "cursor_label",
        "cursor_period_end",
        "sand_period_end",
        "period_end",
        "model",
        "kind",
        "repo",
        "sha",
        "fuel",
        "fuel_mode",
        "working_on",
        "online",
        "status",
        "remaining_pct",
        "account_remaining_pct",
        "cursor_remaining_pct",
        "overage_gbp",
        "overage_usd",
        "overage_fetched_at",
        "overspend_state",
        "on_demand_used_cents",
        "on_demand_limit_cents",
        "on_demand_remaining_pct",
        "grok_account",
        "opencode_account",
        "running",
        "queued",
    ):
        parts.append(f"{key}={peer.get(key)!s}")
    pcent = peer.get("pcent")
    if isinstance(pcent, dict):
        parts.append("pcent=" + json.dumps(pcent, sort_keys=True, separators=(",", ":")))
    else:
        parts.append("pcent=")
    # MRB #6232 / FR #6147: window-only deltas must POST before heartbeat.
    oc_windows = peer.get("opencode_windows")
    if isinstance(oc_windows, dict):
        parts.append(
            "opencode_windows="
            + json.dumps(oc_windows, sort_keys=True, separators=(",", ":"))
        )
    else:
        parts.append("opencode_windows=")
    for key in ("xai_weekly_used_pct", "xai_weekly_source", "xai_weekly_fetched_at"):
        parts.append(f"{key}={peer.get(key)!s}")
    meter = peer.get("xai_weekly")
    if isinstance(meter, dict):
        parts.append("xai_weekly=" + json.dumps(meter, sort_keys=True, separators=(",", ":")))
    else:
        parts.append("xai_weekly=")
    pools = peer.get("cursor_pools")
    if isinstance(pools, list):
        slim = []
        for row in pools:
            if not isinstance(row, dict):
                continue
            slim.append(
                {
                    "group_id": row.get("group_id"),
                    "remaining_pct": row.get("remaining_pct"),
                    "period_end": row.get("period_end"),
                    "machine_id": row.get("machine_id"),
                }
            )
        parts.append("pools=" + json.dumps(slim, sort_keys=True, separators=(",", ":")))
    else:
        parts.append("pools=")
    jobs = peer.get("jobs")
    if isinstance(jobs, list):
        parts.append("jobs=" + json.dumps(jobs, sort_keys=True, separators=(",", ":")))
    else:
        parts.append("jobs=")
    return "|".join(parts)


def build_peer_fuel_merge_payload(peer: dict, machine_id: str) -> dict | None:
    """Build op=merge fuel payload from local bob-peer (FR #6141)."""
    mid = normalize_machine_id(machine_id) or normalize_machine_id(peer.get("id"))
    if not mid or not isinstance(peer, dict):
        return None
    payload: dict = {
        "op": "merge",
        "machine": mid,
        "online": True if peer.get("online", True) else False,
        "status": str(peer.get("status") or "operational"),
    }
    if peer.get("lastSeen"):
        payload["lastSeen"] = str(peer.get("lastSeen"))
    weekly_known = False
    if peer.get("weekly") not in (None, ""):
        try:
            payload["weekly"] = int(peer.get("weekly"))
            weekly_known = True
        except (TypeError, ValueError):
            payload["weekly"] = None
    else:
        payload["weekly"] = None
    if "weekly_known" in peer and peer.get("weekly_known") not in (None, ""):
        weekly_known = bool(peer.get("weekly_known"))
    elif peer.get("weekly_known") is False:
        weekly_known = False
    payload["weekly_known"] = weekly_known
    # FR #6188: forward explicit cursor_known as JSON bool; omit when absent/null.
    cursor_known = _normalize_peer_cursor_known(peer)
    if cursor_known is not None:
        payload["cursor_known"] = cursor_known
    for key in _MERGE_PEER_FIELDS:
        if key in ("weekly", "lastSeen", "online", "status"):
            continue
        if key in peer and peer.get(key) not in (None, ""):
            payload[key] = peer.get(key)
    for key in _FUEL_PUBLISH_EXTRA_FIELDS:
        if key == "weekly_known":
            continue
        if key in peer and peer.get(key) not in (None, ""):
            payload[key] = peer.get(key)
    for key in ("xai_weekly_used_pct", "xai_weekly_source", "xai_weekly_fetched_at"):
        if key in peer:
            payload[key] = peer.get(key)
    # FR #6143 / #6301 / #6309: ear-owned account labels travel with fuel merge.
    # Explicit None/"" must clear sticky digest labels (cleared[]), not omit.
    for key in _EAR_IDENTITY_FIELDS:
        if key not in peer:
            continue
        val = peer.get(key)
        if val in (None, ""):
            payload[key] = None
            cleared = payload.setdefault("cleared", [])
            if isinstance(cleared, list) and key not in cleared:
                cleared.append(key)
            continue
        cleaned = _sanitize_grok_account_label(val)
        if cleaned:
            payload[key] = cleaned
    if isinstance(peer.get("cursor_pools"), list):
        payload["cursor_pools"] = _coerce_cursor_pools(peer.get("cursor_pools"), machine_id=mid)
    blob = json.dumps(payload, separators=(",", ":"), default=str)
    if looks_like_secret(blob):
        return None
    return payload


def report_post_url(env: dict[str, str] | None = None) -> str:
    """Fuel POST URL. Config reportUrl, then BOB_REPORT_URL, then digest default.

    Does not rewrite hostnames. ``irc.ntsa.uk`` stays the IRC host unless that
    string is the configured reportUrl.
    """
    chosen = resolve_fuel_report_target(env=env)
    return str(chosen.get("url") or "")


def resolve_ear_cache_home(
    *,
    explicit_home: str = "",
    install_root: str = "",
    local_system: bool = False,
    userprofile: str = "",
) -> Path:
    """Same home Start-Bob.ps1 passes to ``irc_agent --home``.

    LocalSystem with no ``-BobHome`` uses ``<InstallRoot>\\home``. A user
    session with no ``-BobHome`` uses ``%USERPROFILE%\\.bobiverse``. An
    explicit home wins. This does not look at the Administrator profile.
    """
    raw = (explicit_home or "").strip()
    if raw:
        return Path(raw)
    if local_system:
        root = (install_root or "").strip()
        if not root:
            raise ValueError("local-system ear requires InstallRoot")
        return Path(root) / "home"
    profile = (userprofile or "").strip()
    if not profile:
        raise ValueError("user ear requires a profile")
    return Path(profile) / ".bobiverse"


def _safe_report_target(raw: str, source: str) -> dict:
    """Host and path only. Userinfo, query, and fragment are refused, not stripped."""
    import urllib.parse

    text = (raw or "").strip()
    if not text:
        return {"ok": False, "error": "empty-url", "source": source}
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return {"ok": False, "error": "malformed-url", "source": source}
    if parts.scheme not in ("https", "http"):
        return {"ok": False, "error": "scheme", "source": source}
    if parts.username is not None or parts.password is not None:
        return {"ok": False, "error": "userinfo", "source": source}
    if parts.query or parts.fragment:
        return {"ok": False, "error": "query", "source": source}
    host = parts.hostname
    if not host:
        return {"ok": False, "error": "host", "source": source}
    path = parts.path or "/"
    netloc = host if parts.port is None else f"{host}:{int(parts.port)}"
    url = urllib.parse.urlunsplit((parts.scheme, netloc, path, "", ""))
    return {
        "ok": True,
        "url": url,
        "host": host,
        "path": path,
        "source": source,
        "error": None,
    }


def bobiverse_config_report_url(env: dict[str, str] | None = None) -> str | None:
    """``<BOB_INSTALL_ROOT>/config/bobiverse.json`` reportUrl, or None."""
    e = os.environ if env is None else env
    root = (e.get("BOB_INSTALL_ROOT") or "").strip()
    if not root:
        return None
    path = Path(root) / "config" / "bobiverse.json"
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if not isinstance(doc, dict):
        return None
    raw = doc.get("reportUrl")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def resolve_fuel_report_target(
    url: str | None = None, env: dict[str, str] | None = None
) -> dict:
    """Where the ear fuel POST goes, and which rule chose it.

    Order: explicit url argument, install config reportUrl, BOB_REPORT_URL,
    then the public digest default (``https://bob.ntsa.uk/bob/v1/report``).
    Hosts are not rewritten.
    """
    e = os.environ if env is None else env
    if url and str(url).strip():
        return _safe_report_target(str(url).strip(), "explicit")
    configured = bobiverse_config_report_url(e)
    if configured:
        return _safe_report_target(configured, "config")
    env_url = (e.get("BOB_REPORT_URL") or "").strip()
    if env_url:
        return _safe_report_target(env_url, "env")
    return _safe_report_target(digest_url(), "default")


_last_post_outcome: dict = {}
_last_fuel_publish_diag: dict = {}
_last_xai_acquisition: dict = {}
_last_opencode_acquisition: dict = {}


def last_fuel_publish_diag() -> dict:
    """Last ear fuel publish attempt. No payload values, no secrets."""
    return dict(_last_fuel_publish_diag)


def last_opencode_acquisition() -> dict:
    """Last OpenCode/Go zen acquisition attempt (FR #6263). No secrets."""
    return dict(_last_opencode_acquisition)


def format_fuel_publish_diag(diag: dict | None) -> str:
    """One stdout line. Ack is explicit; a POST word alone is not success."""
    d = diag if isinstance(diag, dict) else {}
    pcent = d.get("pcent_keys") or []
    keys = ",".join(str(k) for k in pcent) if pcent else "-"
    reason = d.get("reason") or "-"
    fields = d.get("provider_fields") or []
    prov = ",".join(str(k) for k in fields) if fields else "-"
    return (
        "home_role={role} target_host={host} target_path={path} url_source={src} "
        "http_status={status} ack={ack} error={error} reason={reason} "
        "pcent_keys={keys} provider_fields={prov} acquisition={acq} "
        "opencode_acquisition={oc_acq} opencode_source={oc_src} "
        "machine={machine} skipped={skipped}"
    ).format(
        role=d.get("home_role") or "unlocalized",
        host=d.get("target_host") or "-",
        path=d.get("target_path") or "-",
        src=d.get("url_source") or "-",
        status=d.get("http_status") if d.get("http_status") is not None else "-",
        ack="true" if d.get("ack") else "false",
        error=d.get("error") or "-",
        reason=str(reason).replace(" ", "_")[:180],
        keys=keys,
        prov=prov,
        acq=d.get("acquisition") or "-",
        oc_acq=d.get("opencode_acquisition") or "-",
        oc_src=d.get("opencode_source") or "-",
        machine=d.get("machine") or "-",
        skipped=d.get("skipped") or "-",
    )


def classify_publish_home(home: Path) -> str:
    """Label the directory a fuel POST would use.

    ``Users/Administrator/.agentic-irc-bobiverse`` is a known non-active cache.
    It is not the LocalSystem service home. Any other path stays ``unlocalized``
    until it matches ``BOB_EAR_HOME`` or ``<BOB_INSTALL_ROOT>/home``.
    """
    parts = [str(p).lower() for p in Path(home).parts]
    if ".agentic-irc-bobiverse" in parts:
        idx = parts.index(".agentic-irc-bobiverse")
        if idx >= 1 and parts[idx - 1] == "administrator":
            return "legacy-admin-not-active"
    try:
        resolved = Path(home).resolve()
    except OSError:
        resolved = Path(home)
    cand = service_publish_home_candidate()
    if cand is not None:
        try:
            if resolved == cand.resolve():
                return "service"
        except OSError:
            if resolved == cand:
                return "service"
    return "unlocalized"


def service_publish_home_candidate() -> Path | None:
    """InstallRoot\\home for LocalSystem ircBob. Empty when it cannot be named."""
    ov = (os.environ.get("BOB_EAR_HOME") or "").strip()
    if ov:
        return Path(ov)
    root = (os.environ.get("BOB_INSTALL_ROOT") or "").strip()
    if root:
        return Path(root) / "home"
    return None


def _record_post_outcome(*, status: int | None, error: str | None, reason: str | None) -> None:
    global _last_post_outcome
    ack = status is not None and 200 <= int(status) < 300
    _last_post_outcome = {
        "http_status": status,
        "ack": ack,
        "error": error,
        "reason": reason,
    }


def post_report_json(payload: dict, *, url: str | None = None, timeout: float = 15.0) -> int | None:
    """POST JSON to report URL. Returns HTTP status or None on transport failure.

    A ``URLError`` is a transport failure with a reason string. It is not evidence
    that the digest document is absent or that auth was rejected.
    """
    import urllib.error
    import urllib.request

    target = (url or report_post_url()).strip()
    if not target or not isinstance(payload, dict):
        _record_post_outcome(status=None, error="no-target", reason=None)
        return None
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    if looks_like_secret(body.decode("utf-8", "replace")):
        _record_post_outcome(status=None, error="secret-refused", reason=None)
        return None
    try:
        req = urllib.request.Request(
            target,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": DIGEST_HTTP_USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = int(getattr(resp, "status", 0) or 0)
            _record_post_outcome(status=code, error=None, reason=None)
            return code
    except urllib.error.HTTPError as exc:
        try:
            code = int(exc.code)
        except Exception:
            code = None
        _record_post_outcome(status=code, error="HTTPError", reason=None)
        return code
    except urllib.error.URLError as exc:
        why = getattr(exc, "reason", None)
        text = f"{type(why).__name__}:{why}" if why is not None else "URLError"
        _record_post_outcome(status=None, error="URLError", reason=text[:180])
        return None
    except (TimeoutError, OSError, ValueError) as exc:
        _record_post_outcome(status=None, error=type(exc).__name__, reason=str(exc)[:180])
        return None


def build_grok_account_merge_payload(machine_id: str, label: str | None) -> dict:
    """Label-only merge payload (FR #6143). Never includes credentials.

    MRB #6167: do not send ``online`` --- ``_apply_merge_payload`` would flip
    ``status`` to ``I am online`` and churn the machine fingerprint vs fuel POSTs.
    """
    mid = normalize_machine_id(machine_id) or str(machine_id or "").strip().lower()
    payload: dict = {"op": "merge", "machine": mid, "id": mid}
    if label is None:
        payload["grok_account"] = None
        payload["cleared"] = ["grok_account"]
    else:
        payload["grok_account"] = label
    return payload


def publish_grok_account_label(
    machine_id: str,
    label: str | None,
    *,
    url: str | None = None,
    timeout: float = 10.0,
) -> int | None:
    """POST grok_account-only merge. Returns HTTP status on 2xx, else None.

    Logs must never include the label. Caller logs ok/failed without the value.
    """
    payload = build_grok_account_merge_payload(machine_id, label)
    code = post_report_json(payload, url=url, timeout=timeout)
    if code is not None and 200 <= int(code) < 300:
        return int(code)
    return None



def _path_under_meipass(path: Path) -> bool:
    """True when ``path`` is inside a PyInstaller onefile unpack (_MEIPASS / Temp)."""
    mei = getattr(sys, "_MEIPASS", None)
    if not mei:
        return False
    try:
        path.resolve().relative_to(Path(str(mei)).resolve())
    except (OSError, ValueError):
        return False
    return True


def opencode_install_root(env: dict[str, str] | None = None) -> Path | None:
    """Install root for the fuel helper and cache.

    Same order as the ear: ``BOB_INSTALL_ROOT`` (Start-Bob sets this before
    ``bob-ear.exe``), else a frozen ``scripts\\bob-ear.exe`` → parent of
    ``scripts``. ``__file__`` under ``_MEIPASS`` is never the install root.
    """
    e = os.environ if env is None else env
    override = (e.get("BOB_INSTALL_ROOT") or "").strip()
    if override:
        return Path(override)
    if not (getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")):
        return None
    exe = Path(sys.executable).resolve()
    if exe.parent.name.lower() == "scripts":
        return exe.parent.parent
    return exe.parent


def on_disk_bobreport_replaces_embed(*, exe_calls_prefer_install_scripts: bool) -> bool:
    """Whether a copied ``scripts\\bobreport.py`` is the module the ear imports.

    True only when that frozen exe was built with ``prefer_install_scripts_path``
    and is started again. The running MarchHare exe imports bobreport at startup
    from its embed; a script copy is not a sufficient deploy by itself.
    """
    return bool(exe_calls_prefer_install_scripts)


def _resolve_opencode_fuel_helper_ps1(env: dict[str, str] | None = None) -> Path | None:
    """Locate Get-BobOpencodeFuel.ps1 (repo tray/tools or install tools layout)."""
    e = os.environ if env is None else env
    override = (e.get("BOB_OPENCODE_FUEL_HELPER") or "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    # Frozen bob-ear.exe sets __file__ under _MEIPASS. Those parents are Temp,
    # not <install>\\tools.
    if not _path_under_meipass(here):
        candidates.extend(
            [
                here.parents[2] / "bob" / "tray" / "tools" / "Get-BobOpencodeFuel.ps1",
                here.parents[1] / "tray" / "tools" / "Get-BobOpencodeFuel.ps1",
                here.parents[1] / "tools" / "Get-BobOpencodeFuel.ps1",
            ]
        )
    root = opencode_install_root(e)
    if root is not None:
        candidates.extend(
            [
                root / "tray" / "tools" / "Get-BobOpencodeFuel.ps1",
                root / "tools" / "Get-BobOpencodeFuel.ps1",
                root / "bob" / "tray" / "tools" / "Get-BobOpencodeFuel.ps1",
            ]
        )
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def _clamp_opencode_pcent_value(raw: object) -> int | None:
    """Return 0..100 int, or None when unknown / unparseable (never invent 0 for None)."""
    if raw is None or raw == "":
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return 0
    if v > 100:
        return 100
    return v


# FR #6146 / CodeRabbit Major: never block the ear 5s fuel tick on a slow PowerShell
# helper (Get-BobOpencodeFuel.ps1 can wait up to 25s per opencode stats window).
# Process-level TTL cache + short helper timeout; stale cache returned on miss/timeout.
# FR #6147: cache the full helper/fixture fuel doc (pcent + windows + limiting).
OPENCODE_FUEL_CACHE_ENV = "BOB_OPENCODE_FUEL_CACHE_S"
DEFAULT_OPENCODE_FUEL_CACHE_S = 30.0
OPENCODE_FUEL_HELPER_TIMEOUT_ENV = "BOB_OPENCODE_FUEL_HELPER_TIMEOUT_S"
DEFAULT_OPENCODE_FUEL_HELPER_TIMEOUT_S = 5.0
# The ear fuel tick must not block. The helper itself runs ``opencode models``
# plus two ``opencode stats`` windows (up to 25s each). Waiting the old 5s
# killed that process before it printed JSON, so the digest stayed
# free=null/go=null/windows=null. The helper runs in the background; this is
# only how long a stuck powershell may live. The kill is a process tree so
# opencode children started by that powershell die with it.
OPENCODE_FUEL_HELPER_DEADLINE_S = 120.0
# The frozen bootstrap overlays only bobreport, and only when that file defines
# opencode_install_root. Other on-disk scripts (gitclaim and the rest of the
# ear import closure) stay unused. Do not delete them and do not copy them over
# to chase a reader crash; the embed that matches the exe is what loads.
FROZEN_EAR_FUEL_DEPLOY = {
    "overlay_modules": ("bobreport",),
    "disk_module_shadows_embed": False,
    "do_not_delete_disk_module": True,
    "when_disk_module_present": (
        "scripts/bob-ear.exe",
        "scripts/bobreport.py",
        "tools/Get-BobOpencodeFuel.ps1",
        "scripts/opencode_fuel.py",
    ),
    "when_disk_module_absent": (
        "scripts/bob-ear.exe",
        "tools/Get-BobOpencodeFuel.ps1",
        "scripts/opencode_fuel.py",
    ),
    "cache_rel": "run/opencode-fuel.json",
    "script_copy_sufficient": False,
    "builder": "bob/scripts/Build-BobEar.ps1",
    "entry": "scripts/irc_agent.py",
}
OPENCODE_WINDOWS_FIXTURE_ENV = "BOB_OPENCODE_WINDOWS_FIXTURE"
_opencode_fuel_cache: dict[str, object] = {"at": 0.0, "doc": {}}
# Back-compat alias used by older tests that poke the private cache name.
_opencode_pcent_cache = _opencode_fuel_cache


def _kill_opencode_fuel_process(proc: object) -> None:
    """Stop the helper powershell and, on Windows, the opencode processes it started.

    ``Popen.kill`` stops only powershell.exe. ``Get-BobOpencodeFuel.ps1`` starts
    ``opencode`` as children; a deadline that kills the parent alone leaves them
    running. ``taskkill /T`` is the tree. Tests pass a fake with no ``pid``.
    """
    pid = getattr(proc, "pid", None)
    if os.name == "nt" and isinstance(pid, int) and pid > 0:
        try:
            import subprocess

            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except Exception:
            pass
    try:
        poll = getattr(proc, "poll", None)
        still = True if poll is None else poll() is None
        if still:
            kill = getattr(proc, "kill", None)
            if kill is not None:
                kill()
    except Exception:
        pass


def clear_opencode_pcent_cache() -> None:
    """Reset process OpenCode fuel cache (tests / forced refresh)."""
    proc = _opencode_fuel_cache.get("proc")
    if proc is not None:
        _kill_opencode_fuel_process(proc)
    stdout_path = _opencode_fuel_cache.get("stdout_path")
    if isinstance(stdout_path, str) and stdout_path:
        try:
            os.unlink(stdout_path)
        except OSError:
            pass
    _opencode_fuel_cache["at"] = 0.0
    _opencode_fuel_cache["doc"] = {}
    _opencode_fuel_cache["value"] = {}
    _opencode_fuel_cache["proc"] = None
    _opencode_fuel_cache["proc_started"] = 0.0
    _opencode_fuel_cache["stdout_path"] = ""


def opencode_fuel_cache_s(env: dict[str, str] | None = None) -> float:
    e = os.environ if env is None else env
    raw = (e.get(OPENCODE_FUEL_CACHE_ENV) or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_OPENCODE_FUEL_CACHE_S


def opencode_fuel_helper_timeout_s(env: dict[str, str] | None = None) -> float:
    e = os.environ if env is None else env
    raw = (e.get(OPENCODE_FUEL_HELPER_TIMEOUT_ENV) or "").strip()
    if raw:
        try:
            return max(0.5, min(30.0, float(raw)))
        except ValueError:
            pass
    return DEFAULT_OPENCODE_FUEL_HELPER_TIMEOUT_S


def _pcent_from_opencode_fuel_doc(doc: dict | None) -> dict[str, int]:
    """Extract known ``opencode-free`` / ``opencode-go`` ints from a fuel doc."""
    out: dict[str, int] = {}
    if not isinstance(doc, dict):
        return out
    mapping = (
        ("opencode-free", ("opencode-free", "free")),
        ("opencode-go", ("opencode-go", "go")),
    )
    for dest, keys in mapping:
        raw = None
        for k in keys:
            if k in doc and doc.get(k) not in (None, ""):
                raw = doc.get(k)
                break
        clamped = _clamp_opencode_pcent_value(raw)
        if clamped is not None:
            out[dest] = clamped
    return out


def _windows_from_opencode_fuel_doc(doc: dict | None) -> dict:
    """Normalize Go windows from a fuel doc, or {} when absent."""
    if not isinstance(doc, dict):
        return {}
    raw = doc.get("windows")
    if not isinstance(raw, dict) or not raw:
        return {}
    try:
        import opencode_fuel as of
    except ImportError:
        return {}
    try:
        return of.normalize_go_windows(raw)
    except Exception:
        return {}


def _apply_windows_fixture(doc: dict, windows_fixture: str) -> dict:
    """Merge ``BOB_OPENCODE_WINDOWS_FIXTURE`` JSON into a fuel doc."""
    text = (windows_fixture or "").strip()
    if not text:
        return doc
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return doc
    if not isinstance(parsed, dict):
        return doc
    # Allow either a bare windows map or a wrapper ``{"windows": {...}}``.
    raw_windows = parsed.get("windows") if isinstance(parsed.get("windows"), dict) else parsed
    if not isinstance(raw_windows, dict):
        return doc
    try:
        import opencode_fuel as of
    except ImportError:
        return doc
    try:
        windows = of.normalize_go_windows(raw_windows)
    except Exception:
        return doc
    out = dict(doc)
    out["windows"] = windows
    lim_id, lim_rem = of.limiting_go_window(windows)
    out["limiting"] = lim_id
    if lim_rem is not None:
        # MRB #6232: never overstate vs model-based remain.
        cur = out.get("opencode-go")
        try:
            cur_i = int(cur) if cur is not None else None
        except (TypeError, ValueError):
            cur_i = None
        chosen = int(lim_rem) if cur_i is None else min(cur_i, int(lim_rem))
        out["opencode-go"] = chosen
        out["go"] = chosen
    return out


def _parse_opencode_helper_stdout(raw_out: str) -> dict:
    """Parse Get-BobOpencodeFuel.ps1 JSON into a full fuel doc (FR #6146 / #6147)."""
    out: dict = {}
    text = (raw_out or "").strip()
    if not text:
        return out
    line = text.splitlines()[-1].strip()
    try:
        doc = json.loads(line)
    except (json.JSONDecodeError, TypeError, ValueError):
        return out
    if not isinstance(doc, dict):
        return out
    out.update(_pcent_from_opencode_fuel_doc(doc))
    windows = _windows_from_opencode_fuel_doc(doc)
    if windows:
        out["windows"] = windows
        try:
            import opencode_fuel as of

            lim_id, lim_rem = of.limiting_go_window(windows)
            out["limiting"] = lim_id
            # Honest go remaining from limiting window when known.
            if lim_rem is not None:
                # MRB #6232: never overstate vs model-based remain.
                cur = out.get("opencode-go")
                try:
                    cur_i = int(cur) if cur is not None else None
                except (TypeError, ValueError):
                    cur_i = None
                out["opencode-go"] = (
                    int(lim_rem) if cur_i is None else min(cur_i, int(lim_rem))
                )
        except Exception:
            if doc.get("limiting") not in (None, ""):
                out["limiting"] = str(doc.get("limiting"))
    elif doc.get("limiting") not in (None, ""):
        out["limiting"] = str(doc.get("limiting"))
    if doc.get("fetched_at") not in (None, ""):
        out["fetched_at"] = str(doc.get("fetched_at"))
    if doc.get("read_state") not in (None, ""):
        out["read_state"] = str(doc.get("read_state"))
    costs = doc.get("local_costs")
    if isinstance(costs, dict) and costs:
        out["local_costs"] = {
            str(k): float(v) for k, v in costs.items() if v not in (None, "")
        }
    hist = doc.get("history")
    if isinstance(hist, dict):
        out["history"] = {
            "sessions": hist.get("sessions"),
            "messages": hist.get("messages"),
            "empty": bool(hist.get("empty")),
        }
    return out


def _read_opencode_fuel_doc_from_fixture(fixture: str) -> dict:
    """Build a full fuel doc from ``BOB_OPENCODE_FUEL_FIXTURE`` (FR #6146 / #6147).

    Rich JSON may carry a top-level ``windows`` object (clarification fixture).
    Free/go still derive from costs/free_models when present; limiting window
    remaining overrides go when known so exhausted week stays honest.
    """
    out: dict = {}
    try:
        import opencode_fuel as of
    except ImportError:
        return out
    parsed_json = None
    try:
        parsed_json = json.loads(fixture)
    except (json.JSONDecodeError, TypeError, ValueError):
        parsed_json = None
    explicit_windows = None
    if isinstance(parsed_json, dict) and isinstance(parsed_json.get("windows"), dict):
        try:
            explicit_windows = of.normalize_go_windows(parsed_json["windows"])
        except Exception:
            explicit_windows = None
    try:
        stats = of.parse_opencode_stats_text_or_json(fixture)
        fuel = of.fuel_from_stats(stats)
    except Exception:
        fuel = {}
    for key in (of.FUEL_ID_FREE, of.FUEL_ID_GO):
        clamped = _clamp_opencode_pcent_value(fuel.get(key))
        if clamped is not None:
            out[key] = clamped
    if explicit_windows is not None:
        out["windows"] = explicit_windows
        lim_id, lim_rem = of.limiting_go_window(explicit_windows)
        out["limiting"] = lim_id
        if lim_rem is not None:
            # MRB #6232: never overstate vs model-based remain.
            cur = out.get(of.FUEL_ID_GO)
            try:
                cur_i = int(cur) if cur is not None else None
            except (TypeError, ValueError):
                cur_i = None
            out[of.FUEL_ID_GO] = (
                int(lim_rem) if cur_i is None else min(cur_i, int(lim_rem))
            )
    elif isinstance(fuel.get("windows"), dict):
        try:
            out["windows"] = of.normalize_go_windows(fuel["windows"])
        except Exception:
            out["windows"] = dict(fuel["windows"])
        if fuel.get("limiting") not in (None, ""):
            out["limiting"] = fuel.get("limiting")
    return out


def _opencode_fuel_cache_file(
    env: dict[str, str] | None, helper: Path | None = None
) -> Path | None:
    """Shared tray/ear cache. Only when an install root or explicit path is set.

    A helper that merely lives in a temp directory must not create ``run/``
    outside that test. The installed layout is ``<root>\\tools\\Get-BobOpencodeFuel.ps1``
    writing ``<root>\\run\\opencode-fuel.json``.
    """
    e = os.environ if env is None else env
    override = (e.get("BOB_OPENCODE_FUEL_CACHE_FILE") or "").strip()
    if override:
        return Path(override)
    root = opencode_install_root(e)
    if root is not None:
        return root / "run" / "opencode-fuel.json"
    if helper is not None and not _path_under_meipass(helper):
        parent = helper.resolve().parent
        if parent.name.lower() == "tools":
            return parent.parent / "run" / "opencode-fuel.json"
    return None


def _opencode_fuel_doc_has_signal(doc: dict | None) -> bool:
    """True when a fuel doc carries a real reading (not an all-unknown shell)."""
    if not isinstance(doc, dict):
        return False
    if _pcent_from_opencode_fuel_doc(doc):
        return True
    wins = doc.get("windows")
    if not isinstance(wins, dict):
        return False
    for rec in wins.values():
        if not isinstance(rec, dict):
            continue
        status = str(rec.get("status") or "unknown").strip().lower()
        if status not in ("unknown", ""):
            return True
        if rec.get("remaining_pct") not in (None, ""):
            return True
    return False


def _load_opencode_fuel_disk(env: dict[str, str], helper: Path | None) -> dict:
    path = _opencode_fuel_cache_file(env, helper)
    if path is None or not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return _parse_opencode_helper_stdout(text)


def _store_opencode_fuel_doc(
    doc: dict, ts: float, env: dict[str, str], helper: Path | None
) -> None:
    stored = dict(doc)
    _opencode_fuel_cache["at"] = ts
    _opencode_fuel_cache["doc"] = stored
    _opencode_fuel_cache["value"] = _pcent_from_opencode_fuel_doc(stored)
    path = _opencode_fuel_cache_file(env, helper)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(stored, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(tmp, path)
    except OSError:
        return


def _drop_opencode_fuel_proc() -> None:
    path = _opencode_fuel_cache.get("stdout_path")
    _opencode_fuel_cache["proc"] = None
    _opencode_fuel_cache["proc_started"] = 0.0
    _opencode_fuel_cache["stdout_path"] = ""
    if isinstance(path, str) and path:
        try:
            os.unlink(path)
        except OSError:
            pass


def _start_opencode_fuel_helper(helper: Path, env: dict[str, str], now: float) -> bool:
    """Start Get-BobOpencodeFuel.ps1 and return without waiting.

    A 5s ``subprocess.run`` timeout killed ``opencode stats`` before the helper
    printed JSON (three sequential CLI calls, 25s each). The ear tick only
    polls. ``poll()`` returning immediately covers unit-test stubs.
    """
    try:
        import subprocess
        import tempfile
    except ImportError:
        return False
    if _opencode_fuel_cache.get("proc") is not None:
        return True
    try:
        fd, name = tempfile.mkstemp(prefix="oc-fuel-", suffix=".out")
        os.close(fd)
        fh = open(name, "w", encoding="utf-8")
    except OSError:
        return False
    try:
        proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
            ],
            stdout=fh,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env={**dict(os.environ), **dict(env)},
        )
    except (OSError, ValueError):
        try:
            fh.close()
        except OSError:
            pass
        try:
            os.unlink(name)
        except OSError:
            pass
        return False
    try:
        fh.close()
    except OSError:
        pass
    _opencode_fuel_cache["proc"] = proc
    _opencode_fuel_cache["proc_started"] = now
    _opencode_fuel_cache["stdout_path"] = name
    return True


def _take_opencode_fuel_helper(now: float) -> tuple[str, dict]:
    """Poll the background helper.

    Returns ``("idle", {})`` when nothing is running, ``("running", {})`` while
    it is still working, ``("doc", parsed)`` when it has exited, or
    ``("failed", {})`` when it was killed for exceeding the deadline.
    """
    proc = _opencode_fuel_cache.get("proc")
    if proc is None:
        return "idle", {}
    started = float(_opencode_fuel_cache.get("proc_started") or now)
    try:
        code = proc.poll()
    except Exception:
        code = None
    if code is None:
        if (now - started) >= OPENCODE_FUEL_HELPER_DEADLINE_S:
            _kill_opencode_fuel_process(proc)
            _drop_opencode_fuel_proc()
            return "failed", {}
        return "running", {}
    path = _opencode_fuel_cache.get("stdout_path")
    text = ""
    if isinstance(path, str) and path:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    _drop_opencode_fuel_proc()
    return "doc", _parse_opencode_helper_stdout(text)


def _accept_opencode_fuel_doc(fresh: dict, cached: dict) -> dict:
    """Keep the last real reading when a failed helper returns an empty shell.

    A completed ``read_state=ok`` document is the new truth, even if some
    windows are unknown. A missing binary must not wipe week/month numbers.
    """
    if not isinstance(fresh, dict):
        return dict(cached) if isinstance(cached, dict) else {}
    fresh_hist = fresh.get("history") if isinstance(fresh.get("history"), dict) else {}
    cached_costs = cached.get("local_costs") if isinstance(cached, dict) else None
    cached_hist = cached.get("history") if isinstance(cached, dict) and isinstance(cached.get("history"), dict) else {}
    cached_sessions = 0
    try:
        cached_sessions = int(cached_hist.get("sessions") or 0)
    except (TypeError, ValueError):
        cached_sessions = 0
    # A service process's empty opencode stats must not replace the user's local history.
    if fresh_hist.get("empty") is True and (
        (isinstance(cached_costs, dict) and cached_costs) or cached_sessions > 0
    ):
        return dict(cached)
    if (
        not _opencode_fuel_doc_has_signal(fresh)
        and _opencode_fuel_doc_has_signal(cached)
        and str(fresh.get("read_state") or "") != "ok"
    ):
        return dict(cached)
    return dict(fresh)


def _read_opencode_fuel_doc_from_helper(
    helper: Path, env: dict[str, str], timeout_s: float
) -> dict:
    """Back-compat wrapper. ``timeout_s`` is not a wait: the helper is polled.

    The historical signature kept the short-timeout argument so older callers
    still import. The ear path no longer blocks on it.
    """
    del timeout_s
    now = time.time()
    status, doc = _take_opencode_fuel_helper(now)
    if status == "doc":
        return doc
    if status == "running":
        return {}
    if not _start_opencode_fuel_helper(helper, env, now):
        return {}
    status, doc = _take_opencode_fuel_helper(now)
    if status == "doc":
        return doc
    return {}


def _read_opencode_pcent_from_fixture(fixture: str) -> dict[str, int]:
    """Back-compat: pcent ints only from a fuel fixture string."""
    return _pcent_from_opencode_fuel_doc(_read_opencode_fuel_doc_from_fixture(fixture))


def _read_opencode_pcent_from_helper(
    helper: Path, env: dict[str, str], timeout_s: float
) -> dict[str, int]:
    """Back-compat: pcent ints only from the PowerShell helper."""
    return _pcent_from_opencode_fuel_doc(
        _read_opencode_fuel_doc_from_helper(helper, env, timeout_s)
    )



# FR #6301 Part D: labelled OpenCode Go keys under config\opencode-keys\<label>.apikey.
# Legacy single-key sources (env + config\opencode-go.apikey) map to label "default".
OPENCODE_KEYS_DIRNAME = "opencode-keys"
OPENCODE_KEY_SELECTED_NAME = "selected.txt"
OPENCODE_KEY_SELECTED_LEGACY = "opencode-key-selected"
OPENCODE_DEFAULT_LABEL = "default"
OPENCODE_NO_KEY_STATE = "no key set"
_OPENCODE_LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]{0,63}$")


def _sanitize_opencode_key_label(raw: object) -> str | None:
    """Safe label for digest / file stem. Never a secret."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or len(text) > 64:
        return None
    if not _OPENCODE_LABEL_RE.match(text):
        return None
    lowered = text.lower()
    if lowered in {"selected", "selected.txt", "readme", "readme.txt"}:
        return None
    return text


def opencode_keys_dir(install_root: str | Path | None, env: dict[str, str] | None = None) -> Path | None:
    """Return ``<InstallRoot>\\config\\opencode-keys`` or None when root unknown."""
    e = os.environ if env is None else env
    root = (str(install_root) if install_root else (e.get("BOB_INSTALL_ROOT") or "")).strip()
    if not root:
        return None
    return Path(root) / "config" / OPENCODE_KEYS_DIRNAME


def _read_opencode_key_file(path: Path) -> str:
    """Read and trim one apikey file. Never logs the value."""
    try:
        if not path.is_file():
            return ""
        return (path.read_text(encoding="utf-8-sig") or "").strip()
    except OSError:
        return ""


def _opencode_key_acl_is_system_admins_only(path: Path) -> bool | None:
    """True when DACL is SYSTEM+Administrators only; None when icacls unavailable."""
    if os.name != "nt" or not path.exists():
        return None
    try:
        r = subprocess.run(
            ["icacls", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    blob = (r.stdout or "") + "\n" + (r.stderr or "")
    lowered = blob.lower()
    # Broad principals mean the ACL is looser than SYSTEM+Administrators.
    for needle in (
        "everyone",
        "authenticated users",
        "builtin\\users",
        "nt authority\\authenticated users",
        "users:",
    ):
        if needle in lowered:
            return False
    has_system = ("nt authority\\system" in lowered) or ("system:" in lowered)
    has_admins = ("builtin\\administrators" in lowered) or ("administrators:" in lowered)
    if not (has_system and has_admins):
        return False
    return True


def tighten_opencode_key_acl(path: Path) -> bool:
    """Force SYSTEM+Administrators-only ACL. Returns True when icacls ran and tightened/set.

    Reports via acquisition stamp when callers record the label; never logs key text.
    """
    if os.name != "nt" or not path.exists():
        return False
    already = _opencode_key_acl_is_system_admins_only(path)
    if already is True:
        return False
    try:
        r = subprocess.run(
            [
                "icacls",
                str(path),
                "/inheritance:r",
                "/grant:r",
                "NT AUTHORITY\\SYSTEM:(F)",
                "/grant:r",
                "BUILTIN\\Administrators:(F)",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def _list_labelled_opencode_keys(
    keys_dir: Path,
    *,
    tighten: bool = True,
) -> tuple[dict[str, str], list[str]]:
    """Return ({label: key}, labels_whose_acl_were_tightened). Keys never logged."""
    out: dict[str, str] = {}
    tightened: list[str] = []
    if not keys_dir.is_dir():
        return out, tightened
    try:
        entries = sorted(keys_dir.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return out, tightened
    for path in entries:
        if not path.is_file():
            continue
        name = path.name
        if not name.lower().endswith(".apikey"):
            continue
        label = _sanitize_opencode_key_label(name[: -len(".apikey")])
        if not label:
            continue
        key = _read_opencode_key_file(path)
        if not key:
            continue
        if tighten and tighten_opencode_key_acl(path):
            tightened.append(label)
        # First wins on case-insensitive collision.
        if label.lower() not in {k.lower() for k in out}:
            out[label] = key
    return out, tightened


def _read_opencode_selected_label(
    install_root: str | Path,
    keys_dir: Path | None,
    env: dict[str, str] | None = None,
) -> str | None:
    """Selected label from selected.txt, legacy file, or BOB_OPENCODE_KEY_LABEL."""
    e = os.environ if env is None else env
    env_label = _sanitize_opencode_key_label(e.get("BOB_OPENCODE_KEY_LABEL") or "")
    if env_label:
        return env_label
    candidates: list[Path] = []
    if keys_dir is not None:
        candidates.append(keys_dir / OPENCODE_KEY_SELECTED_NAME)
    root = Path(install_root)
    candidates.append(root / "config" / OPENCODE_KEY_SELECTED_LEGACY)
    for path in candidates:
        try:
            if not path.is_file():
                continue
            raw = (path.read_text(encoding="utf-8-sig") or "").strip().splitlines()
            if not raw:
                continue
            label = _sanitize_opencode_key_label(raw[0].strip())
            if label:
                return label
        except OSError:
            continue
    return None


def resolve_opencode_go_api_key(
    env: dict[str, str] | None = None,
    *,
    install_root: str | Path | None = None,
) -> tuple[str, str]:
    """Return (api_key, key_source) for Go zen usage (FR #6263 / #6301 Part D).

    key_source is ``env``, ``config-file``, ``labelled-file``, or empty when absent.
    Never logs the key. Prefer ``resolve_opencode_go_api_key_selection`` for label.
    """
    sel = resolve_opencode_go_api_key_selection(env, install_root=install_root)
    return str(sel.get("api_key") or ""), str(sel.get("key_source") or "")


def resolve_opencode_go_api_key_selection(
    env: dict[str, str] | None = None,
    *,
    install_root: str | Path | None = None,
    tighten_acl: bool = True,
) -> dict:
    """FR #6301 Part D: labelled store + legacy default sources.

    Returns dict with api_key, key_source, label, labels, acl_tightened, key_fingerprint.
    ``key_fingerprint`` is a short non-reversible token for cache invalidation only.
    Never includes raw key material in logs/digest fields beyond api_key for the caller.
    Same key in env + legacy file is reported once as label ``default``.
    """
    e = os.environ if env is None else env
    root = (str(install_root) if install_root else (e.get("BOB_INSTALL_ROOT") or "")).strip()
    keys_dir = opencode_keys_dir(root or None, e) if root else None
    labelled: dict[str, str] = {}
    tightened: list[str] = []
    if keys_dir is not None:
        labelled, tightened = _list_labelled_opencode_keys(keys_dir, tighten=tighten_acl)

    env_key = (e.get("BOB_OPENCODE_GO_API_KEY") or "").strip()
    file_key = ""
    legacy_path = Path(root) / "config" / "opencode-go.apikey" if root else None
    if legacy_path is not None:
        file_key = _read_opencode_key_file(legacy_path)
        if file_key and tighten_acl and tighten_opencode_key_acl(legacy_path):
            tightened.append(OPENCODE_DEFAULT_LABEL)

    # Legacy sources collapse to one "default" entry (same key reported once).
    default_key = ""
    default_source = ""
    if env_key and file_key and env_key == file_key:
        default_key = env_key
        default_source = "env"
    elif env_key:
        default_key = env_key
        default_source = "env"
    elif file_key:
        default_key = file_key
        default_source = "config-file"

    # If labelled store already has "default", do not duplicate the same material.
    if default_key:
        existing_default = None
        for lab, val in labelled.items():
            if lab.lower() == OPENCODE_DEFAULT_LABEL:
                existing_default = val
                break
        if existing_default is None:
            labelled[OPENCODE_DEFAULT_LABEL] = default_key
        elif existing_default == default_key:
            pass  # same key once
        # else: labelled default wins; legacy ignored for selection material

    labels = sorted(labelled.keys(), key=lambda s: s.lower())
    selected = _read_opencode_selected_label(root, keys_dir, e) if root else None
    chosen_label = ""
    chosen_key = ""
    key_source = ""
    if selected:
        for lab, val in labelled.items():
            if lab.lower() == selected.lower():
                chosen_label = lab
                chosen_key = val
                key_source = (
                    default_source
                    if lab.lower() == OPENCODE_DEFAULT_LABEL and default_key == val
                    else "labelled-file"
                )
                if lab.lower() == OPENCODE_DEFAULT_LABEL and default_source:
                    key_source = default_source
                break
    if not chosen_key and labelled:
        # No/invalid selection: prefer explicit default, else first label.
        if OPENCODE_DEFAULT_LABEL in labelled:
            chosen_label = OPENCODE_DEFAULT_LABEL
            chosen_key = labelled[OPENCODE_DEFAULT_LABEL]
            key_source = default_source or "labelled-file"
        else:
            # Case-insensitive default
            for lab, val in labelled.items():
                if lab.lower() == OPENCODE_DEFAULT_LABEL:
                    chosen_label = lab
                    chosen_key = val
                    key_source = default_source or "labelled-file"
                    break
        if not chosen_key:
            chosen_label = labels[0]
            chosen_key = labelled[chosen_label]
            key_source = "labelled-file"

    # Fingerprint for cache bust (length + stable hash of key; never the key).
    fp = ""
    if chosen_key:
        try:
            fp = hashlib.sha256(chosen_key.encode("utf-8")).hexdigest()[:16]
        except Exception:
            fp = str(len(chosen_key))

    return {
        "api_key": chosen_key,
        "key_source": key_source if chosen_key else "",
        "label": chosen_label if chosen_key else "",
        "labels": labels,
        "acl_tightened": list(tightened),
        "key_fingerprint": fp,
        "configured": bool(chosen_key),
    }


def _stamp_opencode_acquisition(**fields) -> None:
    global _last_opencode_acquisition
    clean = {
        k: v
        for k, v in fields.items()
        if k
        not in {
            "api_key",
            "key",
            "authorization",
            "secret",
            "BOB_OPENCODE_GO_API_KEY",
        }
    }
    # Never retain raw key material if a caller slipped it in.
    for bad in list(clean):
        if "key" in bad.lower() and bad not in {
            "key_source",
            "key_fingerprint",
            "missing_key",
            "labelled_keys",
        }:
            if isinstance(clean.get(bad), str) and len(str(clean.get(bad))) > 32:
                clean.pop(bad, None)
    _last_opencode_acquisition = dict(clean)


def _no_key_opencode_fuel_doc(*, fetched_at: str | None = None) -> dict:
    """Honest fuel doc when no Go key is configured (FR #6301 Part D)."""
    fetched = fetched_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        import opencode_fuel as of

        windows = of._unknown_provider_windows()  # noqa: SLF001
    except Exception:
        windows = {
            wid: {
                "status": "unknown",
                "used_pct": None,
                "remaining_pct": None,
                "reset_label": None,
                "fetched_at": fetched,
            }
            for wid in ("rolling", "week", "month")
        }
    for wid, rec in list(windows.items()):
        if isinstance(rec, dict):
            row = dict(rec)
            row["error"] = OPENCODE_NO_KEY_STATE
            row["fetched_at"] = fetched
            row["reset_label"] = None
            row["resets_at"] = None
            windows[wid] = row
    return {
        "pcent": {},
        "windows": windows,
        "source": "no-key",
        "fetched_at": fetched,
        "provider_read": "missing_key",
        "opencode_account": None,
        "opencode_state": OPENCODE_NO_KEY_STATE,
    }


def read_local_opencode_fuel_doc(
    env: dict[str, str] | None = None,
    *,
    now: float | None = None,
    force: bool = False,
) -> dict:
    """Read full local OpenCode fuel doc (pcent + windows + limiting; FR #6147).

    Fixtures: ``BOB_OPENCODE_FUEL_FIXTURE`` (stats/rich JSON) and optional
    ``BOB_OPENCODE_WINDOWS_FIXTURE`` (pure windows JSON). The PowerShell helper
    is started in the background and polled. The ear tick does not wait on
    ``opencode stats``. A helper that is still running returns the last
    completed document and does not replace it with an empty shell.
    """
    e = os.environ if env is None else env
    # FR #6248 / #6263: service-owned official Go zen usage (fixture or Bearer key).
    # Tray helper / handoff is not the acquisition path.
    zen_fixture = (e.get("BOB_OPENCODE_GO_USAGE_FIXTURE") or "").strip()
    if zen_fixture:
        try:
            import opencode_fuel as of

            status_s, _, body = zen_fixture.partition("\n")
            if status_s.strip().isdigit() and body:
                status_i = int(status_s.strip())
                payload = body
            else:
                status_i = 200
                payload = zen_fixture
            read = of.interpret_go_zen_usage_response(status_i, payload)
            doc = of.fuel_doc_from_go_zen_read(read)
            kind = read.get("kind") if isinstance(read, dict) else "unavailable"
            _stamp_opencode_acquisition(
                kind=kind,
                configured=True,
                key_source="fixture",
                source=of.GO_ZEN_USAGE_SOURCE,
            )
            return doc
        except Exception:
            _stamp_opencode_acquisition(kind="unavailable", configured=True, key_source="fixture")
            return {}
    sel = resolve_opencode_go_api_key_selection(e)
    api_key = str(sel.get("api_key") or "")
    key_source = str(sel.get("key_source") or "")
    account_label = str(sel.get("label") or "")
    key_fp = str(sel.get("key_fingerprint") or "")
    acl_tightened = list(sel.get("acl_tightened") or [])
    if api_key:
        # FR #6248 / MRB #6252: Bearer zen fetch must honour opencode_fuel_cache_s
        # (digest fuel ticks every ~5s). Keep last good go-zen doc on failure.
        # FR #6301: bust cache when selected label / key fingerprint changes (no restart).
        import opencode_fuel as of

        ts = float(time.time() if now is None else now)
        cache_s = opencode_fuel_cache_s(e)
        last_at = float(_opencode_fuel_cache.get("at") or 0.0)
        last_doc = _opencode_fuel_cache.get("doc")
        if not isinstance(last_doc, dict):
            last_doc = {}
        cached = dict(last_doc)
        cache_fp = str(_opencode_fuel_cache.get("key_fingerprint") or "")
        cache_label = str(_opencode_fuel_cache.get("label") or "")
        same_key = cache_fp == key_fp and cache_label == account_label
        if (
            not force
            and same_key
            and cache_s > 0
            and last_at > 0
            and (ts - last_at) < cache_s
            and str(cached.get("source") or "") == of.GO_ZEN_USAGE_SOURCE
        ):
            _stamp_opencode_acquisition(
                kind=str(cached.get("provider_read") or "json"),
                configured=True,
                key_source=key_source,
                label=account_label,
                source=of.GO_ZEN_USAGE_SOURCE,
                cache="hit",
                acl_tightened=acl_tightened or None,
                labels=list(sel.get("labels") or []),
            )
            out = dict(cached)
            if account_label:
                out["opencode_account"] = account_label
            return out
        try:
            read = of.fetch_go_zen_usage(
                api_key,
                url=(e.get("BOB_OPENCODE_GO_USAGE_URL") or "").strip() or None,
            )
            doc = of.fuel_doc_from_go_zen_read(read)
            if isinstance(doc, dict) and account_label:
                doc["opencode_account"] = account_label
            kind = read.get("kind") if isinstance(read, dict) else None
            _stamp_opencode_acquisition(
                kind=kind or "unavailable",
                configured=True,
                key_source=key_source,
                label=account_label,
                source=of.GO_ZEN_USAGE_SOURCE,
                schema=(read or {}).get("schema") if isinstance(read, dict) else None,
                acl_tightened=acl_tightened or None,
                labels=list(sel.get("labels") or []),
            )
            if kind == "json" and isinstance(doc, dict) and doc:
                _opencode_fuel_cache["at"] = ts
                _opencode_fuel_cache["doc"] = dict(doc)
                _opencode_fuel_cache["value"] = _pcent_from_opencode_fuel_doc(doc)
                _opencode_fuel_cache["key_fingerprint"] = key_fp
                _opencode_fuel_cache["label"] = account_label
                return dict(doc)
            # Failed provider read: keep last good when present; else return honest unknown doc.
            if (
                same_key
                and str(cached.get("source") or "") == of.GO_ZEN_USAGE_SOURCE
                and cached.get("provider_read") == "json"
            ):
                out = dict(cached)
                if account_label:
                    out["opencode_account"] = account_label
                return out
            if same_key and str(cached.get("source") or "") == of.GO_ZEN_USAGE_SOURCE:
                # Prefer last good windows if any known meter exists.
                wins = cached.get("windows") if isinstance(cached.get("windows"), dict) else {}
                known = any(
                    isinstance(wins.get(w), dict) and wins[w].get("status") in ("known", "exhausted")
                    for w in ("rolling", "week", "month")
                )
                if known:
                    out = dict(cached)
                    if account_label:
                        out["opencode_account"] = account_label
                    return out
            return dict(doc) if isinstance(doc, dict) else {}
        except Exception:
            _stamp_opencode_acquisition(
                kind="unavailable",
                configured=True,
                key_source=key_source,
                label=account_label,
                source=of.GO_ZEN_USAGE_SOURCE,
                acl_tightened=acl_tightened or None,
            )
            if same_key and str(cached.get("source") or "") == of.GO_ZEN_USAGE_SOURCE:
                out = dict(cached)
                if account_label:
                    out["opencode_account"] = account_label
                return out
            return {}
    # FR #6301 Part D: no labelled keys and no legacy default -> "no key set".
    # Do not fall through to the tray CLI helper for Go windows (FR #6285 digest-only).
    _stamp_opencode_acquisition(
        kind="missing_key",
        configured=False,
        key_source="",
        label="",
        opencode_state=OPENCODE_NO_KEY_STATE,
        acl_tightened=acl_tightened or None,
        labels=list(sel.get("labels") or []),
    )
    fixture = (e.get("BOB_OPENCODE_FUEL_FIXTURE") or "").strip()
    win_fixture = (e.get(OPENCODE_WINDOWS_FIXTURE_ENV) or "").strip()
    if fixture:
        doc = _read_opencode_fuel_doc_from_fixture(fixture)
        if win_fixture:
            doc = _apply_windows_fixture(doc, win_fixture)
        return doc
    if win_fixture:
        return _apply_windows_fixture({}, win_fixture)
    # Explicit no-key fuel doc (tests / machines without Go key).
    return _no_key_opencode_fuel_doc()


def read_local_opencode_pcent(
    env: dict[str, str] | None = None,
    *,
    now: float | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Read local OpenCode fuel as digest pcent keys (FR #6146).

    Returns only known readings (``opencode-free`` / ``opencode-go``). Unknown
    values are omitted --- never invent ``0``. Explicit exhausted ``0`` is kept.

    Prefers ``BOB_OPENCODE_FUEL_FIXTURE`` (stats JSON/text via ``opencode_fuel``).
    Otherwise calls ``Get-BobOpencodeFuel.ps1`` when present.

    Helper path uses a short timeout (``BOB_OPENCODE_FUEL_HELPER_TIMEOUT_S``,
    default 5s) and a process TTL cache (``BOB_OPENCODE_FUEL_CACHE_S``, default
    30s) so the ear 5s fuel tick cannot stall the outbox loop on a slow
    ``opencode stats`` (CodeRabbit Major on PR #6176).
    """
    doc = read_local_opencode_fuel_doc(env, now=now, force=force)
    return _pcent_from_opencode_fuel_doc(doc)


def read_local_opencode_windows(
    env: dict[str, str] | None = None,
    *,
    now: float | None = None,
    force: bool = False,
) -> dict:
    """Read normalized OpenCode Go windows (FR #6147), or {} when unknown."""
    doc = read_local_opencode_fuel_doc(env, now=now, force=force)
    return _windows_from_opencode_fuel_doc(doc)


def enrich_peer_with_opencode_pcent(
    peer: dict,
    opencode_pcent: dict[str, int] | None = None,
    opencode_windows: dict | None = None,
) -> dict:
    """Merge known OpenCode pcent + windows into a peer copy (FR #6146 / #6147).

    Omits unknown pcent keys; keeps explicit ``0`` (exhausted). Does not invent
    zeros. Sets ``opencode_windows`` when a normalized windows map is supplied.
    """
    if not isinstance(peer, dict):
        return peer
    enriched = dict(peer)
    oc = opencode_pcent if isinstance(opencode_pcent, dict) else {}
    if oc:
        base = enriched.get("pcent") if isinstance(enriched.get("pcent"), dict) else {}
        pcent = dict(base)
        for key in ("opencode-free", "opencode-go"):
            if key not in oc:
                continue
            clamped = _clamp_opencode_pcent_value(oc.get(key))
            if clamped is None:
                continue
            pcent[key] = clamped
        enriched["pcent"] = pcent
    wins_in = opencode_windows
    if wins_in is None and isinstance(oc.get("windows"), dict):
        wins_in = oc.get("windows")
    if isinstance(wins_in, dict) and wins_in:
        try:
            import opencode_fuel as of

            normalized = of.normalize_go_windows(wins_in)
        except Exception:
            normalized = dict(wins_in)
        if normalized:
            enriched["opencode_windows"] = normalized
    return enriched


_XAI_WEEKLY_BILLING_MARK = "billing: fetched credits config"


def meter_sample_is_stale(
    fetched_at: object,
    *,
    now: datetime,
    max_age_s: float,
    last_seen: object = None,
) -> bool:
    """True when the billing sample is too old to paint as current.

    ``last_seen`` is the service heartbeat. It is not the measurement clock
    and cannot make an old sample current.
    """
    del last_seen
    parsed = _parse_iso_ts(fetched_at)
    if parsed is None:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    clock = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return (clock - parsed.astimezone(timezone.utc)).total_seconds() > float(max_age_s)


def _is_windows_system_profile(path: Path) -> bool:
    """LocalSystem's profile. It is not the interactive user's Grok home."""
    text = str(path).replace("/", "\\").lower()
    return "\\systemprofile\\" in text or text.endswith("\\systemprofile")


def _is_local_system_process() -> bool:
    """True when this process is Windows LocalSystem (live service), not a test USERPROFILE spoof.

    Unit tests often set USERPROFILE to systemprofile while USERNAME stays the
    interactive login; those must not auto-open Users\\* (keep system-profile-skipped
    unless BOB_GROK_WEEKLY_USER_HOME / BOB_WEEKLY_LOG is set).
    """
    if os.name != "nt":
        return False
    name = (os.environ.get("USERNAME") or "").strip().upper()
    if name in ("SYSTEM",):
        return True
    # LocalSystem / computer account often appears as COMPUTERNAME$
    if name.endswith("$"):
        return True
    return False


def _interactive_grok_user_home() -> Path | None:
    """FR #6270: interactive console user home that owns ``.grok`` (usage log only; never auth.json).

    Honours ``BOB_GROK_WEEKLY_USER_HOME``. Otherwise resolves Win32 console user /
    explorer owner and returns that Users\\<name> directory when it exists.
    """
    override = (os.environ.get("BOB_GROK_WEEKLY_USER_HOME") or "").strip().rstrip("\\/")
    if override:
        return Path(override)
    if os.name != "nt":
        return None
    account = None
    try:
        import subprocess

        # Avoid PowerShell; keep ASCII + short timeout for the ear tick.
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "$u=$null; try { $u=(Get-CimInstance Win32_ComputerSystem -EA Stop).UserName } catch {}; "
                    "if (-not $u) { $e=Get-CimInstance Win32_Process -Filter \"Name='explorer.exe'\" -EA SilentlyContinue | "
                    "Select-Object -First 1; if ($e) { $o=Invoke-CimMethod -InputObject $e -MethodName GetOwner -EA SilentlyContinue; "
                    "if ($o -and $o.User) { $u= if ($o.Domain) { \"$($o.Domain)\\$($o.User)\" } else { $o.User } } } }; "
                    "if ($u) { Write-Output $u }"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        line = (r.stdout or "").strip().splitlines()
        if line:
            account = line[-1].strip()
    except Exception:
        account = None
    if not account:
        return None
    user = account.split("\\")[-1].strip()
    if not user or user.upper() in ("SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE"):
        return None
    drive = (os.environ.get("SystemDrive") or "C:").rstrip("\\/")
    cand = Path(drive) / "Users" / user
    if cand.is_dir():
        return cand
    return None


def xai_weekly_log_candidate() -> tuple[Path | None, str]:
    """Where a service may read the weekly billing line.

    ``BOB_WEEKLY_LOG`` is an explicit file. Otherwise the process profile's
    ``.grok/logs/unified.jsonl`` is used when that profile is not LocalSystem's
    ``systemprofile``. FR #6270: a live LocalSystem ear (or
    ``BOB_GROK_WEEKLY_USER_HOME``) may read the signed-in interactive user's
    unified.jsonl (usage log only; never auth/credentials).
    """
    raw = (os.environ.get("BOB_WEEKLY_LOG") or "").strip()
    if raw:
        path = Path(raw)
        if _is_windows_system_profile(path):
            return None, "system-profile-refused"
        return path, "explicit"
    exe = (os.environ.get("BOB_GROK_EXE") or "").lower()
    if "fake-grok" in exe:
        return None, "fake-grok"
    home = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
    if not home:
        return None, "no-profile"
    if _is_windows_system_profile(Path(home)):
        # Prefer explicit interactive home (tests + NSSM AppEnvironmentExtra).
        override = (os.environ.get("BOB_GROK_WEEKLY_USER_HOME") or "").strip()
        allow_auto = _is_local_system_process() and not (
            (os.environ.get("BOB_WEEKLY_FORCE_SYSTEM_PROFILE") or "").strip().lower()
            in ("1", "true", "yes", "on")
        )
        user_home = None
        if override or allow_auto:
            user_home = _interactive_grok_user_home()
        if user_home is not None:
            log = user_home / ".grok" / "logs" / "unified.jsonl"
            if log.is_file():
                return log, "interactive-profile"
        return None, "system-profile-skipped"
    return Path(home) / ".grok" / "logs" / "unified.jsonl", "process-profile"


def xai_weekly_log_path() -> Path | None:
    path, _identity = xai_weekly_log_candidate()
    return path


def xai_weekly_handoff_path(env: dict[str, str] | None = None) -> Path | None:
    """Legacy tray handoff path (FR #6248: not an acquisition source).

    Kept for parsers/tests of old files. ``read_local_xai_weekly`` does not
    load this. Service owns measurement via ``BOB_WEEKLY_LOG`` or a non-system
    process profile.
    """
    e = os.environ if env is None else env
    raw = (e.get("BOB_XAI_WEEKLY_FILE") or "").strip()
    if raw:
        return Path(raw)
    root = (e.get("BOB_INSTALL_ROOT") or "").strip()
    if not root:
        return None
    return Path(root) / "run" / "xai-weekly.json"


def parse_xai_weekly_handoff(doc: object, *, now: datetime | None = None) -> dict | None:
    """Meter document from the collector. Missing percent stays unknown, not 0.

    A torn write (``WriteAllText`` is not atomic) fails JSON parse and is ignored.
    ``account`` is not a match key: the collector always leaves it null.
    """
    if not isinstance(doc, dict):
        return None
    if str(doc.get("provider") or "") != "xai":
        return None
    window = str(doc.get("window") or "")
    direction = str(doc.get("direction") or "")
    if not window or direction != "remaining":
        return None
    known = bool(doc.get("weekly_known"))
    remaining = doc.get("remaining_pct")
    used = doc.get("used_pct")
    if known:
        try:
            remaining_i = int(remaining)
            if not 0 <= remaining_i <= 100:
                return None
        except (TypeError, ValueError):
            return None
    else:
        remaining_i = None
    used_i = None
    if used not in (None, ""):
        try:
            used_i = int(used)
        except (TypeError, ValueError):
            used_i = None
    reading = {
        "remaining_pct": remaining_i,
        "used_pct": used_i,
        "period_end": str(doc["period_end"]) if doc.get("period_end") else None,
        "fetched_at": str(doc["fetched_at"]) if doc.get("fetched_at") else None,
        "source": str(doc.get("source") or "collector-handoff"),
        "weekly_known": known and remaining_i is not None,
        "provider": "xai",
        "window": window,
        "direction": "remaining",
        "account": None,
    }
    pe = _parse_xai_period_end(reading.get("period_end"))
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    if pe is not None and pe <= clock.astimezone(timezone.utc):
        reading["remaining_pct"] = None
        reading["used_pct"] = None
        reading["weekly_known"] = False
        reading["stale"] = True
    return reading


def _parse_xai_period_end(raw: object) -> datetime | None:
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_xai_weekly_log_text(text: str, *, now: datetime | None = None) -> dict | None:
    """Last Grok CLI weekly billing event.

    ``creditUsagePercent`` is used percent. ``remaining_pct`` is ``100 - used``.
    A 1.0.41 event with no percent is unknown: remaining stays null, never 0.
    A period that has already ended is unknown, not last week's percent.
    This does not read the grok.com dashboard and does not invent a dashboard figure.
    """
    if not text:
        return None
    raw_line = None
    for line in text.splitlines():
        if _XAI_WEEKLY_BILLING_MARK in line:
            raw_line = line.strip()
    if not raw_line:
        return None
    try:
        doc = json.loads(raw_line)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict):
        return None
    cfg = doc.get("config")
    ctx = doc.get("ctx")
    if not isinstance(cfg, dict) and isinstance(ctx, dict):
        cfg = ctx.get("config")
    if not isinstance(cfg, dict):
        return None
    period = cfg.get("currentPeriod") if isinstance(cfg.get("currentPeriod"), dict) else {}
    ptype = str(period.get("type") or "")
    if "WEEKLY" not in ptype:
        return None
    period_end = period.get("end")
    fetched_at = doc.get("ts")
    used_raw = cfg.get("creditUsagePercent")
    reading: dict = {
        "remaining_pct": None,
        "used_pct": None,
        "period_end": str(period_end) if period_end not in (None, "") else None,
        "fetched_at": str(fetched_at) if fetched_at not in (None, "") else None,
        "source": None,
        "weekly_known": False,
        "provider": "xai",
        "account": None,
    }
    if used_raw not in (None, ""):
        try:
            used = float(used_raw)
        except (TypeError, ValueError):
            used = None
        if used is None or used < 0 or used > 100:
            return None
        used_pct = int(round(used))
        remaining = int(round(100.0 - used))
        if remaining < 0:
            remaining = 0
        if remaining > 100:
            remaining = 100
        reading.update(
            {
                "remaining_pct": remaining,
                "used_pct": used_pct,
                "source": "unified.jsonl:billing:creditUsagePercent",
                "weekly_known": True,
            }
        )
    else:
        has_new = any(k in cfg for k in ("prepaidBalance", "onDemandUsed", "onDemandCap", "isUnifiedBillingUser"))
        if not has_new and not reading["period_end"]:
            return None
        reading["source"] = "unified.jsonl:billing:grok-1.0.41-period"
        reading["weekly_known"] = False
    pe = _parse_xai_period_end(reading.get("period_end"))
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    if pe is not None and pe <= clock.astimezone(timezone.utc):
        reading["remaining_pct"] = None
        reading["used_pct"] = None
        reading["weekly_known"] = False
        reading["stale"] = True
    return reading


def _read_xai_log_file(path: Path, *, now: datetime | None) -> dict | None:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            handle.seek(max(0, size - 1024 * 1024))
            blob = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    return parse_xai_weekly_log_text(blob, now=now)



XAI_BILLING_CREDITS_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
XAI_BILLING_SOURCE = "cli-chat-proxy:/v1/billing?format=credits"


def xai_weekly_auth_path() -> tuple[Path | None, str]:
    """FR #6274: auth.json for the interactive/process Grok session (usage fetch only).

    Never logs or returns credential material - path identity only.
    Honours ``BOB_GROK_AUTH_PATH``, then interactive home (``BOB_GROK_WEEKLY_USER_HOME`` /
    live LocalSystem resolve), else the process profile when it is not systemprofile.
    """
    raw = (os.environ.get("BOB_GROK_AUTH_PATH") or "").strip()
    if raw:
        return Path(raw), "explicit-auth"
    home = (os.environ.get("USERPROFILE") or os.environ.get("HOME") or "").strip()
    if home and _is_windows_system_profile(Path(home)):
        allow_auto = _is_local_system_process() or bool(
            (os.environ.get("BOB_GROK_WEEKLY_USER_HOME") or "").strip()
        )
        if allow_auto:
            user_home = _interactive_grok_user_home()
            if user_home is not None:
                return user_home / ".grok" / "auth.json", "interactive-auth"
        return None, "system-profile-skipped"
    if home:
        return Path(home) / ".grok" / "auth.json", "process-auth"
    return None, "no-profile"



def read_bytes_win32_backup(path: Path) -> tuple[bytes | None, int | None]:
    """FR #6274: read via SeBackupPrivilege + FILE_FLAG_BACKUP_SEMANTICS.

    LocalSystem (ircBob) must read interactive Administrator ``auth.json`` even
    when Grok ``agent.exe`` resets the ACL to Administrator-only. Never changes
    file permissions. Privilege is enabled only for the open/read window.
    Returns ``(data, None)`` on success, ``(None, win32_error)`` on failure.
    Non-Windows returns ``(None, None)`` so callers fall back to a normal open.
    """
    if os.name != "nt":
        return None, None
    import ctypes
    from ctypes import wintypes

    path = Path(path)
    GENERIC_READ = 0x80000000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    TOKEN_QUERY = 0x0008
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    SE_PRIVILEGE_ENABLED = 0x00000002

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", wintypes.DWORD)]

    class TOKEN_PRIVILEGES(ctypes.Structure):
        _fields_ = [
            ("PrivilegeCount", wintypes.DWORD),
            ("Privileges", LUID_AND_ATTRIBUTES * 1),
        ]

    # Private WinDLL handles (bob_worker / FR #3996 pattern): never mutate
    # process-wide ctypes.windll prototypes; use_last_error keeps GetLastError stable.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    # x64: default cdecl int restype truncates HANDLEs (FR #6274 / class of #3996).
    # GetCurrentProcess must be HANDLE too --- without it OpenProcessToken fails
    # with ERROR_INVALID_HANDLE (6) and the backup path never reaches CreateFile.
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
        wintypes.LPVOID,
    ]
    kernel32.GetFileSize.restype = wintypes.DWORD
    kernel32.GetFileSize.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
    advapi32.LookupPrivilegeValueW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.POINTER(LUID),
    ]
    advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL
    # PreviousState / ReturnLength may be NULL when disabling (finally).
    advapi32.AdjustTokenPrivileges.argtypes = [
        wintypes.HANDLE,
        wintypes.BOOL,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]

    def _err() -> int:
        return int(ctypes.get_last_error() or 0)

    def _set_err(code: int = 0) -> None:
        ctypes.set_last_error(int(code))

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(),
        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
        ctypes.byref(token),
    ):
        return None, _err() or 5
    tp = TOKEN_PRIVILEGES()
    tp.PrivilegeCount = 1
    if not advapi32.LookupPrivilegeValueW(
        None, "SeBackupPrivilege", ctypes.byref(tp.Privileges[0].Luid)
    ):
        err = _err() or 1313
        kernel32.CloseHandle(token)
        return None, err
    tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED
    prev = TOKEN_PRIVILEGES()
    prev_size = wintypes.DWORD()
    # Enable; ignore ERROR_NOT_ALL_ASSIGNED (1300) until CreateFile proves it.
    # Interactive seats often lack SeBackupPrivilege; LocalSystem has it.
    _set_err(0)
    advapi32.AdjustTokenPrivileges(
        token,
        False,
        ctypes.byref(tp),
        ctypes.sizeof(prev),
        ctypes.byref(prev),
        ctypes.byref(prev_size),
    )
    adj_err = _err()
    handle = None
    try:
        _set_err(0)
        handle = kernel32.CreateFileW(
            str(path),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        hv = int(handle) if handle is not None else -1
        if hv in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF, 0):
            return None, _err() or adj_err or 5
        size_high = wintypes.DWORD(0)
        _set_err(0)
        size_low = kernel32.GetFileSize(handle, ctypes.byref(size_high))
        if size_low == 0xFFFFFFFF and _err():
            chunks: list[bytes] = []
            buf = ctypes.create_string_buffer(65536)
            read = wintypes.DWORD(0)
            while True:
                _set_err(0)
                if not kernel32.ReadFile(handle, buf, 65536, ctypes.byref(read), None):
                    err = _err()
                    if err in (0, 38):  # EOF
                        break
                    return None, err
                if read.value == 0:
                    break
                chunks.append(buf.raw[: read.value])
            return b"".join(chunks), None
        total = int(size_low) + (int(size_high.value) << 32)
        if total < 0 or total > 8 * 1024 * 1024:
            return None, 12  # ERROR_INVALID_ACCESS / truncate
        if total == 0:
            return b"", None
        buf = ctypes.create_string_buffer(total)
        read = wintypes.DWORD(0)
        _set_err(0)
        if not kernel32.ReadFile(handle, buf, total, ctypes.byref(read), None):
            return None, _err() or 5
        return buf.raw[: read.value], None
    finally:
        try:
            hv = int(handle) if handle is not None else -1
            if hv not in (-1, 0, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                kernel32.CloseHandle(handle)
        except Exception:
            pass
        # Disable privilege again (best effort).
        try:
            tp.Privileges[0].Attributes = 0
            _set_err(0)
            advapi32.AdjustTokenPrivileges(
                token, False, ctypes.byref(tp), 0, None, None
            )
        except Exception:
            pass
        try:
            if token.value:
                kernel32.CloseHandle(token)
        except Exception:
            pass


def read_text_win32_backup(path: Path) -> tuple[str | None, int | None]:
    """UTF-8 text wrapper for :func:`read_bytes_win32_backup`."""
    data, err = read_bytes_win32_backup(path)
    if data is None:
        return None, err
    try:
        return data.decode("utf-8"), None
    except UnicodeError:
        return None, None  # signal bad-json path via caller


def _parse_auth_expires_at(raw: object) -> datetime | None:
    """Parse auth.json expires_at; never logs values."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _auth_entry_bearer(entry: dict) -> str | None:
    """Session bearer from one auth.json entry. Prefer ``key``, else ``access_token``."""
    for name in ("key", "access_token"):
        val = entry.get(name)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _auth_slot_is_api_key(slot: object) -> bool:
    s = str(slot or "").strip().lower()
    return s == "xai::api_key" or s.endswith("::api_key") or s == "api_key"


def load_grok_auth_session(
    path: Path,
) -> tuple[str | None, str | None, str | None]:
    """Load interactive session bearer + label from the *same* auth.json entry.

    Returns ``(token, error, account_label)``. ``error`` is one of:
    ``auth-file-unreadable``, ``auth-file-unreadable:win32-N``,
    ``auth-file-bad-json``, ``auth-key-missing``, or None.
    ``account_label`` is email / name from the selected entry only (FR #6279);
    never borrowed from a sibling entry. Never logs credential values.

    FR #6274: on Windows prefer ``SeBackupPrivilege`` + ``FILE_FLAG_BACKUP_SEMANTICS``
    so LocalSystem can read Administrator-only ``auth.json`` after Grok agent.exe
    strips inherited SYSTEM ACLs. Never changes file permissions. Falls back to a
    normal open when backup read is unavailable (dev seats).

    Layout (Grok CLI / flamingo field names): top-level map keyed by
    ``issuer::client_id``; each entry may carry ``key`` (access token),
    ``refresh_token``, ``expires_at``, profile fields. ``xai::api_key`` slots
    are skipped for the live billing session path. Prefer a non-expired entry.
    """
    raw = None
    win_err: int | None = None
    if os.name == "nt":
        raw, win_err = read_text_win32_backup(path)
        if raw is None and win_err is None:
            # decode failure from backup bytes -> bad json
            return None, "auth-file-bad-json", None
    if raw is None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            if win_err:
                return None, f"auth-file-unreadable:win32-{int(win_err)}", None
            return None, "auth-file-unreadable", None
        except UnicodeError:
            return None, "auth-file-bad-json", None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return None, "auth-file-bad-json", None
    if not isinstance(doc, dict) or not doc:
        return None, "auth-key-missing", None

    now = datetime.now(timezone.utc)
    # rank, token, label (from same entry only)
    candidates: list[tuple[int, str, str | None]] = []
    for slot, entry in doc.items():
        if not isinstance(entry, dict):
            continue
        if _auth_slot_is_api_key(slot):
            continue
        token = _auth_entry_bearer(entry)
        if not token:
            continue
        exp = _parse_auth_expires_at(entry.get("expires_at"))
        # rank: 0 = unexpired / unknown expiry, 1 = expired
        rank = 0
        if exp is not None and exp <= now:
            rank = 1
        label = _label_from_grok_profile(entry)
        candidates.append((rank, token, label))
    if not candidates:
        return None, "auth-key-missing", None
    candidates.sort(key=lambda t: t[0])
    _rank, token, label = candidates[0]
    return token, None, label


def load_grok_auth_bearer(path: Path) -> tuple[str | None, str | None]:
    """Compat: session key only (FR #6274). Prefer ``load_grok_auth_session``."""
    token, err, _label = load_grok_auth_session(path)
    return token, err


def _grok_auth_bearer_from_file(path: Path) -> str | None:
    """Compat wrapper: session key only (FR #6274). Prefer ``load_grok_auth_session``."""
    token, _err, _label = load_grok_auth_session(path)
    return token


def parse_xai_billing_credits_response(
    doc: object, *, now: datetime | None = None
) -> dict | None:
    """Parse CLI ``/v1/billing?format=credits`` into a weekly remaining reading.

    ``creditUsagePercent`` is used percent; remaining is ``100 - used``.
    Absent percent is not a known weekly figure (do not invent 0).
    """
    if not isinstance(doc, dict):
        return None
    cfg = doc.get("config")
    if not isinstance(cfg, dict):
        return None
    used_raw = cfg.get("creditUsagePercent")
    if used_raw is None:
        return None
    try:
        used_f = float(used_raw)
    except (TypeError, ValueError):
        return None
    if not 0.0 <= used_f <= 100.0:
        return None
    used_i = int(round(used_f))
    remaining = max(0, min(100, 100 - used_i))
    period_end = None
    cp = cfg.get("currentPeriod")
    if isinstance(cp, dict) and cp.get("end"):
        period_end = str(cp["end"])
    elif cfg.get("billingPeriodEnd"):
        period_end = str(cfg["billingPeriodEnd"])
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    fetched = clock.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "remaining_pct": remaining,
        "used_pct": used_i,
        "weekly_known": True,
        "period_end": period_end,
        "fetched_at": fetched,
        "source": XAI_BILLING_SOURCE,
        "fresh": True,
        "provider": "xai",
        "window": "weekly",
        "direction": "remaining",
        "account": None,
        "error": None,
    }


def fetch_live_xai_weekly(*, now: datetime | None = None) -> dict | None:
    """FR #6274: live weekly via CLI billing endpoint using the signed-in session.

    Uses auth.json ``key`` in-process only (never copied, printed, or moved).
    Passive unified.jsonl is never treated as a fresh reading.
    """
    global _last_xai_acquisition
    import urllib.error
    import urllib.request

    path, identity = xai_weekly_auth_path()
    if path is None:
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": identity or "auth-missing",
        }
        return None
    if not path.is_file():
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": "auth-file-missing",
        }
        return None
    try:
        token, auth_err, selected_label = load_grok_auth_session(path)
    except OSError:
        token, auth_err, selected_label = None, "auth-file-unreadable", None
    if not token:
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": auth_err or "auth-key-missing",
            "selected": True,
            "account": selected_label,
        }
        return None
    try:
        timeout = float(os.environ.get("BOB_XAI_WEEKLY_FETCH_TIMEOUT_S") or "8")
    except ValueError:
        timeout = 8.0
    timeout = max(1.0, min(timeout, 30.0))
    req = urllib.request.Request(XAI_BILLING_CREDITS_URL, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "xai-grok-cli")
    req.add_header("x-xai-token-auth", "xai-grok-cli")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        # FR #6279: bearer was selected; keep provenance so publish does not
        # fall back to sibling read_grok_account_label on provider failure.
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": f"provider-http-{int(getattr(e, 'code', 0) or 0)}",
            "selected": True,
            "account": selected_label,
        }
        return None
    except Exception as e:
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": f"provider-{type(e).__name__}",
            "selected": True,
            "account": selected_label,
        }
        return None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": "provider-bad-json",
            "selected": True,
            "account": selected_label,
        }
        return None
    reading = parse_xai_billing_credits_response(doc, now=now)
    if not reading:
        _last_xai_acquisition = {
            "identity": identity,
            "read": False,
            "live": False,
            "error": "provider-no-creditUsagePercent",
            "selected": True,
            "account": selected_label,
        }
        return None
    reading["account"] = selected_label
    _last_xai_acquisition = {
        "identity": "live-billing",
        "read": True,
        "live": True,
        "error": None,
        "auth_identity": identity,
        "selected": True,
        "account": selected_label,
    }
    return reading


def enrich_peer_keep_last_good_xai_weekly(
    peer: dict, *, error: str, now: datetime | None = None
) -> dict:
    """FR #6274: on live-fetch failure keep last-good with true age; never blank a knowable value."""
    if not isinstance(peer, dict):
        return peer
    enriched = dict(peer)
    meter = enriched.get("xai_weekly") if isinstance(enriched.get("xai_weekly"), dict) else {}
    last_at = enriched.get("xai_weekly_fetched_at") or meter.get("fetched_at")
    last_rem = enriched.get("weekly")
    if last_rem is None:
        last_rem = meter.get("remaining_pct")
    age_s = None
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    if last_at:
        parsed = _parse_xai_period_end(last_at)
        if parsed is not None:
            age_s = max(0, int((clock - parsed.astimezone(timezone.utc)).total_seconds()))
    rem_i = None
    if last_rem is not None:
        try:
            rem_i = int(last_rem)
        except (TypeError, ValueError):
            rem_i = None
        if rem_i is not None and not 0 <= rem_i <= 100:
            rem_i = None
    pcent = dict(enriched.get("pcent")) if isinstance(enriched.get("pcent"), dict) else {}
    out_meter = {
        "provider": "xai",
        "window": "weekly",
        "direction": "remaining",
        "remaining_pct": rem_i,
        "used_pct": enriched.get("xai_weekly_used_pct")
        if enriched.get("xai_weekly_used_pct") is not None
        else meter.get("used_pct"),
        "source": enriched.get("xai_weekly_source")
        or meter.get("source")
        or "last-good",
        "fetched_at": last_at,
        "period_end": enriched.get("period_end") or meter.get("period_end"),
        "account": None,
        "fresh": False,
        "error": str(error or "live-fetch-failed"),
        "age_s": age_s,
    }
    if rem_i is not None:
        enriched["weekly"] = rem_i
        enriched["weekly_known"] = True
        pcent["grok-build"] = rem_i
    else:
        enriched["weekly"] = None
        enriched["weekly_known"] = False
        pcent.pop("grok-build", None)
    enriched["pcent"] = pcent
    enriched["xai_weekly"] = out_meter
    enriched["xai_weekly_fetched_at"] = last_at
    enriched["xai_weekly_source"] = out_meter.get("source")
    if out_meter.get("used_pct") is not None:
        enriched["xai_weekly_used_pct"] = out_meter.get("used_pct")
    return enriched


def read_local_xai_weekly(*, now: datetime | None = None) -> dict | None:
    """Explicit log, then interactive/process profile unified.jsonl (FR #6270).

    A LocalSystem profile with no explicit file and no interactive user log
    returns None. That is not a measurement and must not be published as a
    fresh weekly (never re-post a carried value as current).
    """
    global _last_xai_acquisition
    path, identity = xai_weekly_log_candidate()
    if identity == "explicit" and path is not None and path.is_file():
        reading = _read_xai_log_file(path, now=now)
        _last_xai_acquisition = {"identity": "explicit", "read": reading is not None}
        if reading:
            return reading
    # FR #6248: tray handoff is not an acquisition path. Service owns the
    # measurement (explicit BOB_WEEKLY_LOG, interactive-profile, or process-profile).
    if identity in ("process-profile", "interactive-profile") and path is not None and path.is_file():
        reading = _read_xai_log_file(path, now=now)
        _last_xai_acquisition = {"identity": identity, "read": reading is not None}
        return reading
    _last_xai_acquisition = {"identity": identity, "read": False}
    return None


def enrich_peer_with_xai_weekly(peer: dict, reading: dict | None) -> dict:
    """Put a measured xAI weekly into the peer as remaining percent.

    ``pcent.grok-build`` and ``weekly`` are remaining, never the used percent
    and never Cursor Sand (``grok-chat``). Unknown does not write 0.
    """
    if not isinstance(peer, dict) or not isinstance(reading, dict):
        return peer
    enriched = dict(peer)
    pcent = dict(enriched.get("pcent")) if isinstance(enriched.get("pcent"), dict) else {}
    # This meter must not be stored as Cursor Sand.
    if reading.get("weekly_known") and reading.get("remaining_pct") is not None:
        try:
            remaining = int(reading["remaining_pct"])
        except (TypeError, ValueError):
            remaining = None
        if remaining is None or not 0 <= remaining <= 100:
            return enriched
        enriched["weekly"] = remaining
        enriched["weekly_known"] = True
        pcent["grok-build"] = remaining
        if reading.get("period_end"):
            enriched["period_end"] = str(reading["period_end"])
        if reading.get("used_pct") is not None:
            enriched["xai_weekly_used_pct"] = int(reading["used_pct"])
        else:
            enriched["xai_weekly_used_pct"] = None
        enriched["xai_weekly_source"] = str(reading.get("source") or "")
        enriched["xai_weekly_fetched_at"] = (
            str(reading["fetched_at"]) if reading.get("fetched_at") else None
        )
        enriched["xai_weekly"] = {
            "provider": "xai",
            "window": str(reading.get("window") or "weekly"),
            "direction": "remaining",
            "remaining_pct": remaining,
            "used_pct": enriched.get("xai_weekly_used_pct"),
            "source": enriched.get("xai_weekly_source"),
            "fetched_at": enriched.get("xai_weekly_fetched_at"),
            "period_end": enriched.get("period_end"),
            "account": reading.get("account"),
            "fresh": bool(reading.get("fresh", True)),
            "error": reading.get("error"),
        }
    else:
        enriched["weekly"] = None
        enriched["weekly_known"] = False
        pcent.pop("grok-build", None)
        enriched["xai_weekly_used_pct"] = None
        enriched["xai_weekly_source"] = str(reading.get("source") or "") or None
        enriched["xai_weekly_fetched_at"] = (
            str(reading["fetched_at"]) if reading.get("fetched_at") else None
        )
        enriched["xai_weekly"] = {
            "provider": "xai",
            "window": str(reading.get("window") or "weekly"),
            "direction": "remaining",
            "remaining_pct": None,
            "used_pct": None,
            "source": enriched.get("xai_weekly_source"),
            "fetched_at": enriched.get("xai_weekly_fetched_at"),
            "period_end": reading.get("period_end"),
            "account": reading.get("account"),
            "fresh": False,
            "error": reading.get("error"),
        }
    enriched["pcent"] = pcent
    return enriched


def publish_local_peer_fuel(
    home: Path,
    machine_id: str,
    *,
    force: bool = False,
    url: str | None = None,
    now: float | None = None,
) -> int | None:
    """POST local peer fuel merge when fingerprint changed or heartbeat due (FR #6141 / #6145 / #6146 / #6147).

    Fingerprint delta always POSTs (``force=True`` or fp change). Unchanged fingerprint
    skips until heartbeat. Max lag pin: ``DIGEST_FUEL_MAX_LAG_S`` (ear delta poll).
    FR #6146 / #6147: enrich with local OpenCode pcent + windows (TTL-cached helper)
    before fingerprint.


    Returns HTTP status on successful 2xx POST, None when skipped or failed.
    """
    global _last_fuel_publish_diag
    mid = normalize_machine_id(machine_id)
    home_role = classify_publish_home(Path(home))
    _last_fuel_publish_diag = {
        "home_role": home_role,
        "machine": mid or "",
        "http_status": None,
        "ack": False,
        "error": None,
        "reason": None,
        "pcent_keys": [],
        "payload_keys": [],
        "provider_fields": [],
        "opencode_acquisition": None,
        "opencode_source": None,
        "target_host": None,
        "target_path": None,
        "url_source": None,
        "home": str(home),
        "skipped": None,
    }
    if home_role == "legacy-admin-not-active":
        # Do not post or rewrite the Administrator legacy cache. It is not the
        # LocalSystem service home, and this path must not be cleared.
        _last_fuel_publish_diag["skipped"] = "legacy-admin-home-not-service"
        return None
    if not mid:
        _last_fuel_publish_diag["skipped"] = "no-machine"
        return None
    peer = bobstat.read_peer(home, mid)
    if not peer:
        return None
    # Refresh Cursor remaining when peer lacks numeric fuel (#70 / FR #6141 gather assist).
    try:
        bobstat.refresh_peer_cursor_remaining(home, mid)
        peer = bobstat.read_peer(home, mid) or peer
    except OSError:
        pass
    # FR #6274: live xAI weekly via CLI billing endpoint (signed-in session key
    # in-memory only). Passive unified.jsonl is never a fresh reading. On failure
    # keep last-good with true age + explicit error (do not blank a knowable value).
    try:
        xai = fetch_live_xai_weekly()
        acq = _last_xai_acquisition.get("identity")
        err = _last_xai_acquisition.get("error")
        _last_fuel_publish_diag["acquisition"] = acq
        if err:
            _last_fuel_publish_diag["xai_weekly_error"] = err
        if xai and xai.get("weekly_known") and xai.get("fresh"):
            peer = enrich_peer_with_xai_weekly(peer, xai)
        else:
            peer = enrich_peer_keep_last_good_xai_weekly(
                peer, error=str(err or acq or "live-fetch-failed")
            )
    except Exception as exc:
        _last_fuel_publish_diag["acquisition"] = "read-failed"
        _last_fuel_publish_diag["xai_weekly_error"] = type(exc).__name__
        peer = enrich_peer_keep_last_good_xai_weekly(peer, error="read-failed")
    # FR #6146 / #6147 / #6248 / #6301: enrich with service-owned OpenCode windows + account label.
    try:
        peer = dict(peer)
        oc_doc = read_local_opencode_fuel_doc()
        oc = _pcent_from_opencode_fuel_doc(oc_doc)
        wins = _windows_from_opencode_fuel_doc(oc_doc)
        if oc or wins:
            peer = enrich_peer_with_opencode_pcent(peer, oc, wins)
        if isinstance(oc_doc, dict) and oc_doc.get("source"):
            _last_fuel_publish_diag["opencode_source"] = str(oc_doc.get("source"))
        acq = last_opencode_acquisition()
        if acq.get("kind"):
            _last_fuel_publish_diag["opencode_acquisition"] = str(acq.get("kind"))
        if acq.get("source") and not _last_fuel_publish_diag.get("opencode_source"):
            _last_fuel_publish_diag["opencode_source"] = str(acq.get("source"))
        if acq.get("acl_tightened"):
            _last_fuel_publish_diag["opencode_acl_tightened"] = True
        # Account label is the selected key label string (never the key).
        label = None
        if isinstance(oc_doc, dict):
            label = oc_doc.get("opencode_account") or acq.get("label")
        else:
            label = acq.get("label")
        cleaned = _sanitize_grok_account_label(label) if label else None
        if cleaned:
            peer["opencode_account"] = cleaned
            _last_fuel_publish_diag["opencode_account_set"] = True
        elif acq.get("kind") == "missing_key" or (
            isinstance(oc_doc, dict) and oc_doc.get("opencode_state") == OPENCODE_NO_KEY_STATE
        ):
            peer["opencode_account"] = None
            if isinstance(peer.get("opencode_windows"), dict):
                # Ensure paint surfaces "no key set" via window error fields.
                wins2 = peer["opencode_windows"]
                for wid, rec in list(wins2.items()):
                    if isinstance(rec, dict) and not rec.get("error"):
                        row = dict(rec)
                        row["error"] = OPENCODE_NO_KEY_STATE
                        wins2[wid] = row
            _last_fuel_publish_diag["opencode_state"] = OPENCODE_NO_KEY_STATE
    except Exception:
        pass
    # FR #6248 / #6279: attach ear-owned grok_account.
    # When this cycle selected an auth entry for live weekly, attribute from that
    # entry only (never borrow a sibling label for the meter). Unlabeled selection
    # stays unattributed. Independent read_grok_account_label is used only when
    # no selection happened this cycle.
    try:
        peer = dict(peer)
        acq = _last_xai_acquisition if isinstance(_last_xai_acquisition, dict) else {}
        selected = bool(acq.get("selected"))
        if selected:
            label = acq.get("account")
            xai_meter = peer.get("xai_weekly")
            if isinstance(xai_meter, dict):
                meter = dict(xai_meter)
                meter["account"] = label
                peer["xai_weekly"] = meter
            if label:
                peer["grok_account"] = label
            else:
                peer.pop("grok_account", None)
        else:
            _src, label = read_grok_account_label()
            if label:
                peer["grok_account"] = label
                xai_meter = peer.get("xai_weekly")
                if isinstance(xai_meter, dict):
                    meter = dict(xai_meter)
                    meter["account"] = label
                    peer["xai_weekly"] = meter
    except Exception:
        pass
    payload = build_peer_fuel_merge_payload(peer, mid)
    if not payload:
        _last_fuel_publish_diag["skipped"] = "no-payload"
        return None
    pcent = payload.get("pcent") if isinstance(payload.get("pcent"), dict) else {}
    _last_fuel_publish_diag["pcent_keys"] = sorted(str(k) for k in pcent)
    _last_fuel_publish_diag["payload_keys"] = sorted(str(k) for k in payload)
    fp = peer_fuel_fingerprint(peer)
    state_path = digest_fuel_post_state_path(home)
    posted: dict = {}
    if state_path.is_file():
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                posted = {str(k): v for k, v in raw.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            posted = {}
    ts_now = float(time.time() if now is None else now)
    last_fp = str(posted.get(mid) or "")
    at_key = mid + "@posted_at"
    last_at = None
    if at_key in posted:
        try:
            last_at = float(posted[at_key])
        except (TypeError, ValueError):
            last_at = None
    heartbeat_s = digest_fuel_heartbeat_s()
    heartbeat_due = False
    if heartbeat_s > 0 and last_fp:
        if last_at is None:
            heartbeat_due = True
        else:
            heartbeat_due = (ts_now - last_at) >= heartbeat_s
    if not force and last_fp == fp and not heartbeat_due:
        _last_fuel_publish_diag["skipped"] = "fingerprint-unchanged"
        return None
    # Heartbeat and change posts both carry a fresh lastSeen. Re-sending the
    # peer file's old lastSeen left the canonical row on the previous day
    # while the HTTP status was still 200.
    payload["lastSeen"] = datetime.fromtimestamp(ts_now, timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )
    target = resolve_fuel_report_target(url)
    _last_fuel_publish_diag["url_source"] = target.get("source")
    _last_fuel_publish_diag["target_host"] = target.get("host")
    _last_fuel_publish_diag["target_path"] = target.get("path")
    meter = payload.get("xai_weekly") if isinstance(payload.get("xai_weekly"), dict) else {}
    _last_fuel_publish_diag["provider_fields"] = sorted(str(k) for k in meter)
    if not target.get("ok"):
        _last_fuel_publish_diag["skipped"] = "url-rejected"
        _last_fuel_publish_diag["error"] = target.get("error")
        return None
    code = post_report_json(payload, url=str(target.get("url") or ""))
    _last_fuel_publish_diag.update(
        {
            "http_status": _last_post_outcome.get("http_status"),
            "ack": bool(_last_post_outcome.get("ack")),
            "error": _last_post_outcome.get("error"),
            "reason": _last_post_outcome.get("reason"),
        }
    )
    if home_role != "legacy-admin-not-active":
        try:
            diag_path = Path(home) / "digest-fuel-publish-diag.json"
            diag_path.write_text(
                json.dumps(_last_fuel_publish_diag, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass
    if code is not None and 200 <= int(code) < 300:
        posted[mid] = fp
        posted[at_key] = ts_now
        try:
            state_path.write_text(json.dumps(posted, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
        return int(code)
    return None


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
        if _peer_delta_put(payload, key, val):
            changed = True
    for key in ("online", "status", "working_on"):
        val = _peer_delta_value(peer, chair_machine, key)
        if _peer_delta_put(payload, key, val):
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
