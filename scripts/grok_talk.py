#!/usr/bin/env python3
"""Grok-talk enqueue + outbox drain (no grok.exe in irc_agent hot path)."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import bobreport
import bobtalk

GROK_TALK_VERSION = 1
INBOX_NAME = "grok-inbox.jsonl"
OUTBOX_NAME = "grok-outbox.jsonl"
CONFIG_NAME = "grok-talk.json"
LINE_CAP = 350
MENTION_COOLDOWN_S = bobtalk.MENTION_COOLDOWN_S


def inbox_path(home: Path) -> Path:
    return home / INBOX_NAME


def completion_path(home: Path) -> Path:
    return home / OUTBOX_NAME


def config_path(home: Path) -> Path:
    return home / CONFIG_NAME


def grok_talk_enabled(home: Path) -> bool:
    flag = (os.environ.get("AGENTIC_IRC_GROK_TALK") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    p = config_path(home)
    if not p.is_file():
        return False
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(doc.get("grok_talk_enabled") or doc.get("enabled"))


def weekly_fuel_ok(home: Path, machine_id: str) -> bool:
    peer = bobtalk.resolve_peer(home, machine_id)
    if not peer:
        return False
    weekly = peer.get("weekly")
    if weekly is None or weekly == "":
        return False
    try:
        return int(weekly) > 0
    except (TypeError, ValueError):
        return False


def cursor_remaining_ok(home: Path, machine_id: str) -> bool:
    """Cursor Models remaining % > 0. cursor_label is display-only (not fuel)."""
    peer = bobtalk.resolve_peer(home, machine_id)
    if not peer:
        return False
    for key in ("remaining_pct", "account_remaining_pct", "cursor_remaining_pct"):
        raw = peer.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw) > 0
        except (TypeError, ValueError):
            continue
    return False


def fuel_ok(home: Path, machine_id: str) -> bool:
    """Enqueue fuel: Grok weekly > 0 OR Cursor remaining_pct > 0 (#70 MUST 5)."""
    return weekly_fuel_ok(home, machine_id) or cursor_remaining_ok(home, machine_id)


def body_hash(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()[:16]


def reply_target_for(asker: str, channel: str, to_channel: bool) -> str:
    if to_channel:
        dest = bobreport.normalize_channel(channel) or channel
        return dest or channel
    who = (asker or "").strip()
    return who


def mention_eligible(
    machine_id: str,
    nicks: list[str],
    asker: str,
    body: str,
    to_me: bool,
) -> bool:
    if not bobtalk.is_fleet_bob_nick(nicks[0] if nicks else ""):
        return False
    if not bobtalk.should_answer_asker(asker):
        return False
    if bobtalk.is_protocol_line(body):
        return False
    if not bobtalk.addressed_to(body, nicks, to_me=to_me):
        return False
    if bobreport.looks_like_secret(body):
        return False
    return True


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def pending_job_ids(home: Path) -> set[str]:
    inbox = {str(r.get("job_id") or "") for r in _read_jsonl(inbox_path(home))}
    done = {str(r.get("job_id") or "") for r in _read_jsonl(completion_path(home))}
    return {j for j in inbox if j and j not in done}


def should_enqueue(
    home: Path,
    machine_id: str,
    nicks: list[str],
    asker: str,
    body: str,
    to_me: bool,
    dedupe_last: dict[tuple[str, str], float],
    now: float | None = None,
) -> bool:
    if not grok_talk_enabled(home):
        return False
    if not fuel_ok(home, machine_id):
        return False
    if not mention_eligible(machine_id, nicks, asker, body, to_me):
        return False
    if pending_job_ids(home):
        return False
    t = now if now is not None else time.time()
    key = ((asker or "").strip().lower(), body_hash(body))
    last = dedupe_last.get(key, 0.0)
    if t - last < MENTION_COOLDOWN_S:
        return False
    return True


def enqueue_mention(
    home: Path,
    machine_id: str,
    nick: str,
    nicks: list[str],
    asker: str,
    channel: str,
    body: str,
    to_me: bool,
    to_channel: bool,
    dedupe_last: dict[tuple[str, str], float],
    now: float | None = None,
) -> str | None:
    """Append inbox job when gates pass. Returns job_id or None."""
    t = now if now is not None else time.time()
    if not should_enqueue(home, machine_id, nicks, asker, body, to_me, dedupe_last, now=t):
        return None
    job_id = secrets.token_hex(8)
    record = {
        "v": GROK_TALK_VERSION,
        "job_id": job_id,
        "ts": t,
        "asker": (asker or "").strip(),
        "channel": channel,
        "body": body,
        "nick": nick,
        "machine_id": machine_id,
        "reply_target": reply_target_for(asker, channel, to_channel),
        "body_hash": body_hash(body),
    }
    p = inbox_path(home)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    key = ((asker or "").strip().lower(), body_hash(body))
    dedupe_last[key] = t
    return job_id


def format_privmsg_line(target: str, text: str) -> str | None:
    msg = (text or "").replace("\r", " ").replace("\n", " ").strip()
    if not msg or bobreport.looks_like_secret(msg):
        return None
    if len(msg) > LINE_CAP:
        msg = msg[: LINE_CAP - 3] + "..."
    dest = (target or "").strip()
    if not dest or "|" in dest:
        return None
    return f"PRIVMSG {dest} :{msg}"


def drain_completions_to_outbox(home: Path, outbox: Path | None = None) -> list[str]:
    """Read new grok-outbox.jsonl records; append PRIVMSG lines to outbox.txt."""
    comp = completion_path(home)
    if not comp.is_file():
        return []
    pos_path = Path(str(comp) + ".drain.pos")
    last = 0
    if pos_path.is_file():
        try:
            last = int(pos_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            last = 0
    raw = comp.read_bytes()
    if last > len(raw):
        last = 0
    chunk = raw[last:]
    if not chunk:
        return []
    lines_out: list[str] = []
    ob = outbox or (home / "outbox.txt")
    buf = chunk.decode("utf-8", errors="replace")
    for row in buf.splitlines():
        text = row.strip()
        if not text:
            continue
        try:
            doc = json.loads(text)
        except json.JSONDecodeError:
            continue
        if int(doc.get("v") or 0) != GROK_TALK_VERSION:
            continue
        target = str(doc.get("reply_target") or "").strip()
        for fact in doc.get("lines") or []:
            wire = format_privmsg_line(target, str(fact))
            if wire:
                lines_out.append(wire)
    if lines_out:
        with ob.open("a", encoding="utf-8") as f:
            for wire in lines_out:
                f.write(wire + "\n")
    pos_path.write_text(str(last + len(chunk)) + "\n", encoding="utf-8")
    return lines_out
