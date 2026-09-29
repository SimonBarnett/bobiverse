#!/usr/bin/env python3
"""Conversational English lines from bob-peers JSON (one fact per line)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import bobstat

FLEET_MOOT_ID = "b0b1be15e0000001"
FLEET_MACHINE_ORDER = ("flamingo", "marchhare", "ionos", "ce-priority-dev1")
BOBIVERSE_CMD = "!bobiverse"
RECYCLE_CMD = "!recycle"
BOBIVERSE_COOLDOWN_S = 60.0
BOBIVERSE_AGENT_COOLDOWN_S = 120.0
MENTION_COOLDOWN_S = 20.0
TRAY_PREFIX = "BOB TRAY v1 "
_PROTOCOL_HEADS = (
    "agpk v1 ",
    "seal v1 ",
    "seal v2 ",
    "file v1 ",
    "dumb v1 ",
    "capa v1 ",
    "bob tray v1 ",
    "bob digest v1 ",
    "bob v1 ",
    "recycle v1 ",
    "moot v1 point ",
    "moot v1 open ",
    "moot v1 join ",
    "moot v1 part ",
    "moot v1 floor ",
    "moot v1 yield ",
    "moot v1 close ",
    "moot v1 roll ",
    "moot v1 roster ",
    "moot v1 handoff ",
    "!bobiverse",
    "!recycle",
    "!report",
    "!bored",
    "!accept",
    "!task",
)

_ID_ALIASES = {"dev1": "ce-priority-dev1", "ce-priority-dev1": "ce-priority-dev1"}


def display_id(machine_id: str) -> str:
    mid = str(machine_id or "").strip()
    if mid == "ce-priority-dev1":
        return "dev1"
    return mid or "?"


def briefer_nick(moot_state: dict, online_nicks: set[str] | None = None) -> str | None:
    """Chair if bob-*, else first online bob-* on roster, else first bob-*."""
    roster = list(moot_state.get("roster") or [])
    chair = str(moot_state.get("chair") or "").strip()
    if chair.lower().startswith("bob-"):
        return chair
    online = {n.lower() for n in (online_nicks or set())}
    fallback: str | None = None
    for nick in roster:
        n = str(nick)
        if not n.lower().startswith("bob-"):
            continue
        if fallback is None:
            fallback = n
        if not online or n.lower() in online:
            return n
    return fallback


def is_briefer(moot_state: dict, live_nick: str, online_nicks: set[str] | None = None) -> bool:
    bn = briefer_nick(moot_state, online_nicks)
    if bn:
        return live_nick.lower() == bn.lower()
    return live_nick.lower().startswith("bob-")


def is_digest_operator(
    moot_state: dict, live_nick: str, online_nicks: set[str] | None, home: Path
) -> bool:
    """Digest merge + !bobiverse: dedicated chair when configured (issue #73)."""
    import bobreport as br

    chair = br.digest_chair_nick(home)
    if chair:
        return live_nick.lower() == chair.lower()
    return is_briefer(moot_state, live_nick, online_nicks)


def fleet_status_to_channel_enabled(home: Path) -> bool:
    """No fleet ACTION / join brief on #bobiverse when digest chair is configured."""
    import bobreport as br

    return not br.chair_mode_active(home)


def parse_bobiverse_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == BOBIVERSE_CMD


def parse_recycle_command(body: str) -> bool:
    text = (body or "").strip()
    if not text:
        return False
    return text.split(None, 1)[0].lower() == RECYCLE_CMD


def is_tray_asker(nick: str) -> bool:
    """Fleet agents / Watch / shop workers use tray pull (~120s)."""
    n = (nick or "").strip().lower()
    return n.startswith("bob-") or n.startswith("w-")


def _repo_ok(repo: object) -> bool:
    s = str(repo or "").strip()
    return bool(s) and s not in ("?", "-")


def resolve_peer(home: Path, machine_id: str) -> dict | None:
    mid = _ID_ALIASES.get(machine_id, machine_id)
    peer = bobstat.read_peer(home, mid)
    if peer:
        return peer
    if mid != machine_id:
        return bobstat.read_peer(home, machine_id)
    return None


def _resolve_peer_id(home: Path, machine_id: str) -> dict | None:
    return resolve_peer(home, machine_id)


def list_fleet_peers(home: Path) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for mid in FLEET_MACHINE_ORDER:
        peer = _resolve_peer_id(home, mid)
        if peer and peer.get("id") not in seen:
            out.append(peer)
            seen.add(str(peer.get("id")))
    d = bobstat.peers_dir(home)
    if d.is_dir():
        for path in sorted(d.glob("*.json")):
            try:
                doc = bobstat.read_peer(home, path.stem)
            except OSError:
                continue
            if doc and str(doc.get("id")) not in seen:
                out.append(doc)
                seen.add(str(doc.get("id")))
    return out


def _running_job(peer: dict) -> dict | None:
    for j in list(peer.get("jobs") or []):
        if str(j.get("state", "")).lower() == "running":
            return j
    return None


def effective_repo(peer: dict, job: dict | None = None) -> str | None:
    """Top-level repo, else running job — never treat '?' as known."""
    if _repo_ok(peer.get("repo")):
        return str(peer.get("repo")).strip()
    j = job if job is not None else _running_job(peer)
    if j and _repo_ok(j.get("repo")):
        return str(j.get("repo")).strip()
    for j in list(peer.get("jobs") or []):
        if _repo_ok(j.get("repo")):
            return str(j.get("repo")).strip()
    return None


def _infer_model(peer: dict) -> str | None:
    model = peer.get("model")
    if model:
        return str(model)
    cur = peer.get("cursor_label")
    if cur and str(cur) not in ("", "-", "empty"):
        return "Cursor Models"
    job = _running_job(peer)
    if job:
        repo = str(job.get("repo") or "")
        if repo == "grok.exe":
            return "grok.exe"
    run = int(peer.get("running") or 0)
    if run > 0:
        return "grok.exe"
    return None


def _short_sha(sha: str) -> str:
    s = str(sha or "").strip()
    if len(s) > 7:
        return s[:7]
    return s


def _human_duration(peer: dict) -> str | None:
    dur = peer.get("duration")
    if dur:
        return str(dur)
    started = peer.get("started_at") or peer.get("started")
    if not started:
        return None
    try:
        if isinstance(started, (int, float)):
            t0 = datetime.fromtimestamp(float(started), tz=timezone.utc)
        else:
            raw = str(started).replace("Z", "+00:00")
            t0 = datetime.fromisoformat(raw)
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    secs = max(0, int((datetime.now(timezone.utc) - t0).total_seconds()))
    if secs < 90:
        return f"{secs} seconds"
    mins = secs // 60
    if mins < 90:
        return f"{mins} minutes" if mins != 1 else "1 minute"
    hours = mins // 60
    if hours == 1:
        return "an hour"
    return f"{hours} hours"


def _kind_phrase(kind: str, repo: str) -> str | None:
    k = (kind or "").strip().lower()
    if not repo:
        return None
    if k == "mrb":
        return f"That's an MRB of {repo}."
    if k == "uat":
        return f"That's UAT on {repo}."
    if k == "worker":
        return f"That's a worker on {repo}."
    return f"Working on {repo}."


def peer_talk_lines(peer: dict | None) -> list[str]:
    """FR #341: no IRC status talk (idle/busy/model/repo). Digest webhook only.

    Kept as a named API for callers; always returns an empty list so join-briefs
    and mention ACKs never announce worker busy/idle on the wire.
    """
    return []


def network_talk_lines(home: Path) -> list[str]:
    """FR #341: join brief must not dump idle/busy lines onto IRC."""
    return []


def _tray_jobs_field(peer: dict) -> str:
    parts: list[str] = []
    for j in list(peer.get("jobs") or []):
        repo = effective_repo({"repo": j.get("repo")}, j) or ""
        state = str(j.get("state") or "running").replace(" ", "")
        if repo and state:
            parts.append(f"{repo}:{state}")
    return ",".join(parts) if parts else "-"


def format_tray_peer_line(peer: dict) -> str:
    """One machine-readable line for tray / bob-peers refresh (no secrets)."""
    mid = str(peer.get("id") or "").strip()
    running = int(peer.get("running") or 0)
    queued = int(peer.get("queued") or 0)
    weekly = peer.get("weekly")
    w = "-" if weekly is None or weekly == "" else str(int(weekly))
    repo = effective_repo(peer) or "-"
    kind = str(peer.get("kind") or "-").replace(" ", "")
    model = str(peer.get("model") or "-").replace(" ", "")
    seen = str(peer.get("lastSeen") or "-")
    return (
        f"{TRAY_PREFIX}id={mid} weekly={w} running={running} queued={queued} "
        f"repo={repo} kind={kind} model={model} lastSeen={seen} jobs={_tray_jobs_field(peer)}"
    )


def tray_pull_lines(home: Path) -> list[str]:
    """Agent !bobiverse answer: last update per fleet machine (whisper to asker)."""
    peers = list_fleet_peers(home)
    if not peers:
        return [f"{TRAY_PREFIX}id=- weekly=- running=0 queued=0 repo=- kind=- model=- lastSeen=- jobs=-"]
    return [format_tray_peer_line(p) for p in peers]


def change_talk_line(before: dict | None, after: dict) -> str | None:
    """FR #341: never emit status-change talk on IRC (digest owns state)."""
    return None


def is_fleet_bob_nick(nick: str) -> bool:
    return str(nick or "").strip().lower().startswith("bob-")


def should_answer_asker(nick: str) -> bool:
    """Do not ping-pong other bob-* Watch nicks. Humans, cursor-*, w-* yes."""
    n = str(nick or "").strip().lower()
    if not n or is_fleet_bob_nick(n):
        return False
    return True


def say_text(body: str) -> str:
    """Channel English, or the trailing text of MOOT v1 SAY."""
    raw = str(body or "").replace("\x01", " ").strip()
    low = raw.lower()
    if low.startswith("moot v1 say "):
        if " :" in raw:
            return raw.split(" :", 1)[1].strip()
        parts = raw.split(None, 4)
        return parts[-1] if len(parts) >= 5 else ""
    return raw


def is_protocol_line(body: str) -> bool:
    text = str(body or "").replace("\x01", " ").strip()
    if not text:
        return True
    low = text.lower()
    if low.startswith("\x01action") or low.startswith("action "):
        return True
    for head in _PROTOCOL_HEADS:
        if low.startswith(head):
            return True
    if low.startswith("moot v1 say "):
        return False
    if low.startswith("moot v1 "):
        return True
    return False


def addressed_to(body: str, nicks: list[str], to_me: bool = False) -> bool:
    if to_me:
        return True
    text = say_text(body)
    if not text:
        return False
    low = text.lower()
    for nick in nicks:
        n = str(nick or "").strip()
        if not n:
            continue
        nl = n.lower()
        if re.search(rf"(?i)(?:^|[\s])@{re.escape(nl)}(?:\b|[:,])", text):
            return True
        if low.startswith(nl + ":") or low.startswith(nl + ","):
            return True
    if re.search(r"(?i)(?:^|[\s])@all\b", text) or re.search(r"(?i)(?:^|[\s])@bobiverse\b", text):
        return True
    return False


def heard_snippet(body: str, nicks: list[str], limit: int = 80) -> str:
    text = say_text(body)
    for nick in nicks:
        n = str(nick or "").strip()
        if n:
            text = re.sub(rf"(?i)@?{re.escape(n)}\s*[:,]?\s*", " ", text)
    text = re.sub(r"(?i)@all\b|@bobiverse\b", " ", text)
    text = " ".join(text.split()).strip()
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def mention_reply_line(
    home: Path,
    machine_id: str,
    nicks: list[str],
    asker: str,
    body: str,
    to_me: bool = False,
) -> str | None:
    """One English ACK. No grok.exe. weekly=0 still answers."""
    if not is_fleet_bob_nick(nicks[0] if nicks else ""):
        return None
    if not should_answer_asker(asker):
        return None
    if is_protocol_line(body):
        return None
    if not addressed_to(body, nicks, to_me=to_me):
        return None
    mid = display_id(machine_id)
    peer = _resolve_peer_id(home, machine_id) or {}
    # FR #341: mention ACK is presence + weekly only — never idle/busy/model/repo status.
    weekly = peer.get("weekly")
    if weekly is None or weekly == "":
        week = "weekly=-"
    else:
        try:
            w = int(weekly)
        except (TypeError, ValueError):
            w = None
        if w == 0:
            # MUST 5 (#70): weekly=0 still enqueues when Cursor remaining > 0.
            rem = None
            for key in ("remaining_pct", "account_remaining_pct", "cursor_remaining_pct"):
                raw = peer.get(key)
                if raw is None or raw == "":
                    continue
                try:
                    rem = float(raw)
                    break
                except (TypeError, ValueError):
                    continue
            if rem is not None and rem > 0:
                week = f"weekly=0 (cursor remaining={int(rem)}%)"
            else:
                week = "weekly=0 (cannot grok-talk)"
        elif w is None:
            week = "weekly=-"
        else:
            week = f"weekly={w}"
    heard = heard_snippet(body, list(nicks) + ["all", "bobiverse"])
    who = str(asker or "").strip() or "there"
    line = f"@{who} {mid} here. {week}."
    if heard:
        line = f"{line} Heard: {heard}"
    if len(line) > 350:
        line = line[:347] + "..."
    return line
