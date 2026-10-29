"""FR #5164: deterministic Jeeves stall detectors (no agent).

Each detector returns zero or more findings:
``{id, key, title, evidence}``. Fingerprint is ``stall:{id}:{key}``.
"""
from __future__ import annotations

from typing import Any

import gitclaim

SELF_REVIEW_ID = "self-review-deadlock"
ALL_GAVE_UP_ID = "all-gave-up"
STICKY_PIN_ID = "sticky-auto-pin"
RESYNC_FAIL_ID = "resync-fail"
ACK_STALE_ID = "ack-stale"
BORED_LATENCY_ID = "bored-latency"

RESYNC_FAIL_N = 3
ACK_STALE_S = 45 * 60
BORED_LATENCY_S = 240.0


def fingerprint(detector_id: str, key: str) -> str:
    return f"stall:{detector_id}:{key}"


def _author_nicks(row: dict) -> list[str]:
    seats = gitclaim.row_author_seats(row)
    if seats:
        return seats
    found: list[str] = []
    seen: set[str] = set()
    for k in (
        "implementer_seat",
        "mrb_author_seat",
        "author_seat",
        "author_nick",
        "author",
    ):
        raw = str(row.get(k) or "").strip()
        if not raw:
            continue
        nick = gitclaim.canonical_worker_nick(raw) or raw
        key = nick.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(nick)
    return found


def _idle_blocked(row: dict, nick: str, live: set[str], idle: set[str], ledger: dict) -> bool:
    me = (gitclaim.canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return True
    if gitclaim.row_gave_up_by(row, me, live=live):
        return True
    authors = _author_nicks(row)
    if me.lower() in {a.lower() for a in authors}:
        return True
    return bool(
        gitclaim.review_blocked_for_author(row, me, live, ledger=ledger, free=idle)
    )


def _row_id(row: dict) -> str:
    repo = str(row.get("repo") or "").strip()
    ident = str(row.get("ident") or row.get("id") or "").strip()
    url = str(row.get("url") or "")
    pm = gitclaim.PULL_URL_RE.search(url)
    if pm:
        return f"{pm.group('repo')}#{pm.group('num')}"
    im = gitclaim.ISSUE_URL_RE.search(url)
    if im:
        return f"{im.group(1)}#{im.group(2)}"
    if repo and ident:
        num = ident.lstrip("#")
        return f"{repo}#{num}"
    return ident or repo or "unknown"


def detect_self_review_deadlock(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Idle seats exist, every waiting offerable MRB is blocked for every idle seat."""
    idle = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("idle") or [])}
    idle = {n for n in idle if n}
    live = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("live") or [])}
    live = {n for n in live if n} or set(idle)
    if not idle:
        return []
    waiting = []
    for row in snap.get("unaccepted") or []:
        if gitclaim._canon_task(row) != "MRB":
            continue
        if not gitclaim.mrb_row_offerable(row):
            continue
        waiting.append(row)
    if not waiting:
        return []
    ledger = snap.get("ledger") or {}
    for row in waiting:
        for nick in idle:
            if _idle_blocked(row, nick, live, idle, ledger):
                continue
            return []
    keys = ",".join(sorted(_row_id(r) for r in waiting))
    return [
        {
            "id": SELF_REVIEW_ID,
            "key": keys,
            "title": f"stall:self-review-deadlock:{keys}",
            "evidence": {
                "idle": sorted(idle),
                "waiting": [_row_id(r) for r in waiting],
            },
        }
    ]


def detect_all_gave_up(snap: dict[str, Any]) -> list[dict[str, Any]]:
    live = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("live") or [])}
    live = {n for n in live if n}
    if not live:
        return []
    out = []
    for row in list(snap.get("unaccepted") or []) + list(snap.get("accepted") or []):
        if not live:
            break
        if all(gitclaim.row_gave_up_by(row, n, live=live) for n in live):
            rid = _row_id(row)
            out.append(
                {
                    "id": ALL_GAVE_UP_ID,
                    "key": rid,
                    "title": f"stall:all-gave-up:{rid}",
                    "evidence": {"live": sorted(live), "row": rid},
                }
            )
    return out


def detect_sticky_auto_pin(snap: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for row in snap.get("unaccepted") or []:
        stamped = str(row.get("require_machine") or "").strip().lower()
        if not stamped:
            continue
        inferred = gitclaim.infer_require_machine(
            title=str(row.get("title") or ""),
            body=str(row.get("body") or ""),
            labels=row.get("labels") or (),
            repo=str(row.get("repo") or ""),
            ident=str(row.get("ident") or row.get("id") or ""),
        )
        inferred = (inferred or "").strip().lower()
        if inferred == stamped:
            continue
        rid = _row_id(row)
        out.append(
            {
                "id": STICKY_PIN_ID,
                "key": f"{rid}:{stamped}",
                "title": f"stall:sticky-auto-pin:{rid}:{stamped}",
                "evidence": {
                    "row": rid,
                    "stamped": stamped,
                    "inferred": inferred or "",
                },
            }
        )
    return out


def detect_resync_fail(snap: dict[str, Any]) -> list[dict[str, Any]]:
    streak = int(snap.get("resync_fail_streak") or 0)
    if streak < RESYNC_FAIL_N:
        return []
    status = snap.get("last_resync_status")
    return [
        {
            "id": RESYNC_FAIL_ID,
            "key": f"streak-{streak}",
            "title": f"stall:resync-fail:streak-{streak}",
            "evidence": {"streak": streak, "status": status},
        }
    ]


def detect_ack_stale(snap: dict[str, Any]) -> list[dict[str, Any]]:
    now = float(snap.get("now") or 0)
    out = []
    for row in snap.get("accepted") or []:
        acked = float(row.get("acked_at") or row.get("accepted_at") or 0)
        last = float(row.get("last_activity") or acked or 0)
        if not last or now - last < ACK_STALE_S:
            continue
        rid = _row_id(row)
        nick = str(row.get("accepted_by") or row.get("offered_to") or "")
        out.append(
            {
                "id": ACK_STALE_ID,
                "key": rid,
                "title": f"stall:ack-stale:{rid}",
                "evidence": {"row": rid, "nick": nick, "idle_s": int(now - last)},
            }
        )
    return out


def detect_bored_latency(snap: dict[str, Any]) -> list[dict[str, Any]]:
    now = float(snap.get("now") or 0)
    idle = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("idle") or [])}
    last_bored = snap.get("last_bored") or {}
    out = []
    for nick in idle:
        if not nick:
            continue
        ts = last_bored.get(nick)
        if ts is None:
            ts = last_bored.get(nick.lower())
        if ts is None:
            continue
        lag = now - float(ts)
        if lag < BORED_LATENCY_S:
            continue
        out.append(
            {
                "id": BORED_LATENCY_ID,
                "key": nick.lower(),
                "title": f"stall:bored-latency:{nick}",
                "evidence": {"nick": nick, "lag_s": int(lag)},
            }
        )
    return out


DETECTORS = (
    detect_self_review_deadlock,
    detect_all_gave_up,
    detect_sticky_auto_pin,
    detect_resync_fail,
    detect_ack_stale,
    detect_bored_latency,
)


def detect_all(snap: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for fn in DETECTORS:
        found.extend(fn(snap))
    for item in found:
        item["fingerprint"] = fingerprint(item["id"], item["key"])
    return found
