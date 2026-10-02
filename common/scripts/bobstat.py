#!/usr/bin/env python3
"""Cleartext BOB v1 fleet status on a MODE2 moot POINT (not a secret).

Wire (trailing text of MOOT v1 POINT <id> :<text>, <=350 chars):

    BOB v1 id=flamingo weekly=96 running=0 queued=0 lastSeen=2026-09-20T08:31:16Z jobs=-

jobs is '-' or comma-separated repo:state (no spaces). Weekly is that
machine's own Grok weekly remaining percent, or '-' if unknown.
Optional remaining=<0-100> is Cursor Models remaining percent (persisted as
remaining_pct / account_remaining_pct / cursor_remaining_pct on bob-peers).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BOB_PREFIX = "BOB v1 "
MAX_POINT = 350
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
JOB_RE = re.compile(r"^[A-Za-z0-9._+/-]+:[A-Za-z0-9_-]+$")
REMAINING_KEYS = ("remaining_pct", "account_remaining_pct", "cursor_remaining_pct")


def apply_remaining_aliases(doc: dict, remaining: int | float | None) -> dict:
    """Persist Cursor remaining on all three peer aliases (MUST 5 / #70)."""
    if remaining is None or remaining == "":
        return doc
    try:
        n = int(remaining)
    except (TypeError, ValueError):
        return doc
    if n < 0 or n > 100:
        return doc
    for key in REMAINING_KEYS:
        doc[key] = n
    return doc


def normalize_remaining_aliases(doc: dict) -> dict:
    """If any remaining alias is set, write all three. Never parse cursor_label."""
    for key in REMAINING_KEYS:
        raw = doc.get(key)
        if raw is None or raw == "":
            continue
        try:
            return apply_remaining_aliases(doc, float(raw))
        except (TypeError, ValueError):
            continue
    return doc


def _parse_remaining_pct(raw: object) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        return None
    if 0 <= n <= 100:
        return n
    return None


def _pcent_cursor_remaining(doc: dict) -> int | None:
    pcent = doc.get("pcent")
    if not isinstance(pcent, dict):
        return None
    for key in ("cursor-models", "cursor_models", "cursor_models_remaining"):
        n = _parse_remaining_pct(pcent.get(key))
        if n is not None:
            return n
    return None


def numeric_remaining_from_doc(doc: dict) -> int | None:
    """Cursor Models remaining % from peer/POINT fields. Never cursor_label."""
    for key in REMAINING_KEYS + ("remaining",):
        n = _parse_remaining_pct(doc.get(key))
        if n is not None:
            return n
    return _pcent_cursor_remaining(doc)


def coerce_peer_doc(doc: dict) -> dict:
    """Normalize Watch/POINT peer JSON before persist or fuel read."""
    out = dict(doc)
    rem = numeric_remaining_from_doc(out)
    if rem is not None:
        apply_remaining_aliases(out, rem)
    return normalize_remaining_aliases(out)


def merge_preserved_remaining(prev: dict | None, incoming: dict) -> dict:
    """Keep prior numeric remaining when a new POINT/doc omits it."""
    if not prev:
        return incoming
    if any(incoming.get(k) not in (None, "") for k in REMAINING_KEYS):
        return normalize_remaining_aliases(incoming)
    for key in REMAINING_KEYS:
        raw = prev.get(key)
        if raw is None or raw == "":
            continue
        try:
            return apply_remaining_aliases(incoming, float(raw))
        except (TypeError, ValueError):
            continue
    return incoming


def parse_bob_point(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw.startswith(BOB_PREFIX):
        return None
    body = raw[len(BOB_PREFIX) :].strip()
    kv: dict[str, str] = {}
    for tok in body.split():
        if "=" not in tok:
            return None
        k, _, v = tok.partition("=")
        kv[k] = v
    mid = kv.get("id", "")
    if not ID_RE.match(mid):
        return None
    jobs_raw = kv.get("jobs", "-")
    jobs: list[dict] = []
    if jobs_raw and jobs_raw != "-":
        for part in jobs_raw.split(","):
            if not JOB_RE.match(part):
                continue
            repo, _, state = part.partition(":")
            jobs.append({"repo": repo, "state": state, "machine": mid})
    weekly = kv.get("weekly", "-")
    weekly_pct = None
    if weekly not in ("", "-"):
        try:
            n = int(weekly)
            if 0 <= n <= 100:
                weekly_pct = n
        except ValueError:
            weekly_pct = None
    running = 0
    queued = 0
    try:
        running = int(kv.get("running", "0"))
        queued = int(kv.get("queued", "0"))
    except ValueError:
        return None
    remaining_pct = None
    rem_raw = kv.get("remaining") or kv.get("remaining_pct") or kv.get("crem")
    if rem_raw not in (None, "", "-"):
        try:
            n = int(rem_raw)
            if 0 <= n <= 100:
                remaining_pct = n
        except ValueError:
            remaining_pct = None
    cursor_label = None
    cur_raw = kv.get("cur") or kv.get("cursor_label")
    if cur_raw not in (None, "", "-"):
        cursor_label = cur_raw
    cursor_period_end = None
    crst = kv.get("crst") or kv.get("cursor_period_end")
    if crst not in (None, "", "-"):
        cursor_period_end = crst
    out: dict = {
        "ok": True,
        "id": mid,
        "weekly": weekly_pct,
        "running": running,
        "queued": queued,
        "lastSeen": kv.get("lastSeen") or None,
        "jobs": jobs,
        "source": "irc",
    }
    if cursor_label is not None:
        out["cursor_label"] = cursor_label
    if cursor_period_end is not None:
        out["cursor_period_end"] = cursor_period_end
    if remaining_pct is not None:
        apply_remaining_aliases(out, remaining_pct)
    return out


def format_bob_point(doc: dict) -> str:
    mid = str(doc.get("id") or "")
    if not ID_RE.match(mid):
        raise ValueError("invalid machine id")
    weekly = doc.get("weekly")
    if weekly is None or weekly == "":
        w = "-"
    else:
        w = str(int(weekly))
    jobs = []
    for j in list(doc.get("jobs") or []):
        repo = str(j.get("repo") or "").replace(" ", "")
        state = str(j.get("state") or "running").replace(" ", "")
        if repo and state and JOB_RE.match(f"{repo}:{state}"):
            jobs.append(f"{repo}:{state}")
    job_s = ",".join(jobs) if jobs else "-"
    seen = str(doc.get("lastSeen") or "-")
    rem = None
    for key in REMAINING_KEYS:
        raw = doc.get(key)
        if raw is None or raw == "":
            continue
        try:
            rem = int(float(raw))
            break
        except (TypeError, ValueError):
            continue
    rem_s = f" remaining={rem}" if rem is not None else ""
    line = (
        f"{BOB_PREFIX}id={mid} weekly={w} running={int(doc.get('running') or 0)} "
        f"queued={int(doc.get('queued') or 0)} lastSeen={seen} jobs={job_s}{rem_s}"
    )
    if len(line) > MAX_POINT:
        line = line[: MAX_POINT - 1] + "-"
    return line


def peers_dir(home: Path) -> Path:
    d = Path(home) / "bob-peers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_peer(home: Path, doc: dict) -> Path | None:
    parsed = doc if doc.get("ok") and doc.get("id") else parse_bob_point(str(doc.get("text") or ""))
    if not parsed and doc.get("id"):
        parsed = dict(doc)
    if not parsed:
        return None
    path = peers_dir(home) / (parsed["id"] + ".json")
    prev = None
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prev = None
    parsed = coerce_peer_doc(dict(parsed))
    parsed = merge_preserved_remaining(prev, parsed)
    path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
    return path


def read_peer(home: Path, machine_id: str) -> dict | None:
    path = peers_dir(home) / (machine_id + ".json")
    try:
        if not path.exists():
            return None
        return coerce_peer_doc(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def cursor_usage_script_paths() -> list[Path]:
    out: list[Path] = []
    for env in ("AGENTIC_BUILD_ROOT", "BOB_BUILD_ROOT"):
        raw = (os.environ.get(env) or "").strip()
        if raw:
            out.append(Path(raw) / "tools" / "Get-CursorAgentUsage.py")
    for root in (r"C:\ai\agentic_build", r"D:\ai\agentic_build"):
        out.append(Path(root) / "tools" / "Get-CursorAgentUsage.py")
    seen: set[str] = set()
    uniq: list[Path] = []
    for p in out:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def load_cursor_usage_doc() -> dict | None:
    """Sister Get-CursorAgentUsage.py JSON (Cursor Models remaining, not cursor_label)."""
    py = sys.executable
    for script in cursor_usage_script_paths():
        if not script.is_file():
            continue
        try:
            proc = subprocess.run(
                [py, str(script)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        raw = (proc.stdout or "").strip()
        if not raw or raw == "{}":
            continue
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(doc, dict) and doc.get("ok"):
            return doc
    return None


def refresh_peer_cursor_remaining(
    home: Path,
    machine_id: str,
    *,
    usage_doc: dict | None = None,
) -> bool:
    """Persist Cursor remaining on bob-peers when weekly=0 and file lacks numeric fuel."""
    peer = read_peer(home, machine_id)
    if not peer:
        return False
    weekly = peer.get("weekly")
    try:
        if weekly is not None and weekly != "" and int(weekly) > 0:
            return False
    except (TypeError, ValueError):
        pass
    if numeric_remaining_from_doc(peer) not in (None, 0):
        return False
    usage = usage_doc if usage_doc is not None else load_cursor_usage_doc()
    if not usage:
        return False
    rem = _parse_remaining_pct(usage.get("remaining_pct"))
    if rem is None or rem <= 0:
        return False
    merged = coerce_peer_doc(dict(peer))
    apply_remaining_aliases(merged, rem)
    write_peer(home, merged)
    return True
