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
    if snap.get("deadlock_healed"):
        return []
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
    """Report rows abandoned by every live seat unless already parked for a human.

    FR #5181: ``needs_human`` rows are intentional parks — skip them so the
    stall filer does not keep re-alerting (class of a-search#5139).
    """
    live = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("live") or [])}
    live = {n for n in live if n}
    if not live:
        return []
    out = []
    for row in list(snap.get("unaccepted") or []) + list(snap.get("accepted") or []):
        if not isinstance(row, dict):
            continue
        # FR #5181: parked-for-human rows are not actionable stalls.
        if gitclaim.row_needs_human(row):
            continue
        if all(gitclaim.row_gave_up_by(row, n, live=live) for n in live):
            rid = _row_id(row)
            out.append(
                {
                    "id": ALL_GAVE_UP_ID,
                    "key": rid,
                    "title": f"stall:all-gave-up:{rid}",
                    "evidence": {
                        "live": sorted(live),
                        "row": rid,
                        "giveup_seats": sorted(gitclaim.giveup_seat_set(row)),
                        "needs_human": False,
                    },
                }
            )
    return out


def stamp_needs_human_for_all_gave_up(
    home: Any,
    findings: list[dict[str, Any]],
) -> int:
    """FR #5181: park queue rows that just triggered all-gave-up (first alert).

    Returns the number of rows stamped. Subsequent scans skip via
    ``row_needs_human`` in ``detect_all_gave_up``.
    """
    keys = {
        str(f.get("key") or "").strip()
        for f in (findings or [])
        if isinstance(f, dict) and str(f.get("id") or "") == ALL_GAVE_UP_ID
    }
    keys.discard("")
    if not keys:
        return 0
    stamped = 0
    try:
        with gitclaim._lock(home):
            doc = gitclaim._load_queue_unlocked(home)
            changed = False
            for bucket in ("unaccepted", "accepted"):
                for row in list(doc.get(bucket) or []):
                    if not isinstance(row, dict):
                        continue
                    if _row_id(row) not in keys:
                        continue
                    if gitclaim.row_needs_human(row):
                        continue
                    row["needs_human"] = True
                    stamped += 1
                    changed = True
            if changed:
                gitclaim._write_queue(gitclaim.queue_path(home), doc)
    except Exception:
        return 0
    return stamped


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


def _accepted_nicks(snap: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in snap.get("accepted") or []:
        for k in ("accepted_by", "offered_to", "nick"):
            raw = str(row.get(k) or "").strip()
            if not raw:
                continue
            nick = gitclaim.canonical_worker_nick(raw) or raw
            if nick:
                out.add(nick)
                out.add(nick.lower())
    return out


def _has_live_offer(snap: dict[str, Any], nick: str, now: float) -> bool:
    me = (gitclaim.canonical_worker_nick(nick) or nick or "").strip().lower()
    for row in snap.get("unaccepted") or []:
        if not isinstance(row, dict):
            continue
        offered_to = str(row.get("offered_to") or "").strip()
        offered_nick = (
            gitclaim.canonical_worker_nick(offered_to) or offered_to
        ).strip().lower()
        if offered_nick != me or gitclaim._is_lost_done_reoffer_to(row, nick):
            continue
        if gitclaim._offer_age_s(row, now) < gitclaim.offer_timeout_s(row):
            return True
    return False


def detect_bored_latency(snap: dict[str, Any]) -> list[dict[str, Any]]:
    now = float(snap.get("now") or 0)
    idle = {gitclaim.canonical_worker_nick(n) or n for n in (snap.get("idle") or [])}
    last_bored = snap.get("last_bored") or {}
    last_activity = snap.get("last_activity") or {}
    busy = _accepted_nicks(snap)
    out = []
    for nick in idle:
        if not nick:
            continue
        if nick in busy or nick.lower() in busy or _has_live_offer(snap, nick, now):
            continue
        ts = last_bored.get(nick)
        if ts is None:
            ts = last_bored.get(nick.lower())
        act = last_activity.get(nick)
        if act is None:
            act = last_activity.get(nick.lower())
        if act is not None:
            ts = float(act) if ts is None else max(float(ts), float(act))
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
