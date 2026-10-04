#!/usr/bin/env python3
"""Seats stuck in doing/offered (FR #1019): stale busy, NAK loops, aged wire silence."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    iter_worker_entries,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

DOING_MAX_AGE_SEC = 15 * 60
NAK_BUSY_MIN = 3
LOG_TAIL = 400
PERMISSION_RX = re.compile(r"PermissionError|WinError\s*5|Access is denied", re.I)
NAK_BUSY_RX = re.compile(r"bored\s+nak\s+busy", re.I)
WIRE_RX = re.compile(r"\b(ACK|DONE|GIVEUP|NACK)\b", re.I)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _age_sec(stamp) -> float | None:
    if isinstance(stamp, (int, float)):
        v = float(stamp)
        if v > 1_000_000_000_000:
            return time.time() - (v / 1000.0)
        if v > 1_000_000_000:
            return time.time() - v
        return None
    if isinstance(stamp, str) and stamp:
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return time.time() - dt.timestamp()
        except Exception:
            return None
    return None


def _tail_lines(path: Path, n: int = LOG_TAIL) -> list[str]:
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()[-n:]
    except Exception:
        return []


def _worker_busy(w: dict) -> bool:
    state = str(w.get("state") or "").lower()
    if state in ("doing", "offered", "busy", "accepted"):
        return True
    wo = w.get("working_on")
    if wo is None:
        return False
    if isinstance(wo, str):
        return bool(wo.strip())
    if isinstance(wo, dict):
        return bool(wo)
    return bool(wo)


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    remediation = [
        "report only by default (keep seats busy; harvest #1967)",
        "restart BobCallback if digest/working_on is stale",
        "clear_seat_doing / idle workers.<pid>.working_on only when accepted is empty AND seat is a true orphan blocking !bored (use --force-orphan-busy)",
    ]
    stuck = []
    dig = _load_json(digest / "digest.json") or {}
    queue = _load_json(resolve_queue_path(chair, digest)) or {}
    accepted = queue_bucket_rows(queue, "accepted")
    machines = dig.get("machines") if isinstance(dig, dict) else None
    workers = [w for w in iter_worker_entries(machines) if _worker_busy(w)]

    # chair logs: cmd-trace + stdout
    log_lines: list[str] = []
    for name in ("cmd-trace.log", "stdout.log", "chair.log"):
        log_lines.extend(_tail_lines(chair / name))
    # also install-style logs if chair home mirrors them
    perm_count = sum(1 for ln in log_lines[-LOG_TAIL:] if PERMISSION_RX.search(ln))

    # nak busy per nick
    nak_counts: dict[str, int] = {}
    for ln in log_lines:
        if not NAK_BUSY_RX.search(ln):
            continue
        # try to pull nick token
        m = re.search(r"(marchhare|ionos|flamingo|ce-priority-dev1)[-\w]*", ln, re.I)
        nick = m.group(0).lower() if m else "_unknown"
        nak_counts[nick] = nak_counts.get(nick, 0) + 1

    if workers and not accepted:
        for w in workers:
            nick = str(w.get("nick") or w.get("name") or "?")
            findings.append(
                f"digest seat {nick} state={w.get('state')} but queue.accepted is empty (stale busy)"
            )
            stuck.append({"nick": nick, "reason": "stale_busy_empty_accepted", "state": w.get("state")})

    for w in workers:
        nick = str(w.get("nick") or w.get("name") or "?")
        nick_l = nick.lower()
        age = None
        for k in ("state_ts", "doing_ts", "accepted_ts", "offered_ts", "updated", "ts"):
            age = _age_sec(w.get(k))
            if age is not None:
                break
        # fall back to matching accepted row stamp
        if age is None:
            for row in accepted:
                rn = str(row.get("nick") or row.get("accepted_by") or "").lower()
                if rn and rn == nick_l:
                    age = _age_sec(row.get("accepted_ts") or row.get("offered_ts") or row.get("ts"))
                    if age is not None:
                        break
        wire_hits = sum(1 for ln in log_lines if nick_l in ln.lower() and WIRE_RX.search(ln))
        if age is not None and age > DOING_MAX_AGE_SEC and wire_hits == 0:
            findings.append(
                f"seat {nick} doing/offered age_sec={int(age)} (>15m) with no ACK/DONE/GIVEUP in recent chair log"
            )
            stuck.append({"nick": nick, "reason": "aged_no_wire", "age_sec": int(age)})

        nak_n = 0
        for k, v in nak_counts.items():
            if k == nick_l or nick_l.startswith(k) or k in nick_l:
                nak_n += v
        if nak_n >= NAK_BUSY_MIN:
            findings.append(f"seat {nick} bored nak busy repeated {nak_n} times (>= {NAK_BUSY_MIN})")
            stuck.append({"nick": nick, "reason": "nak_busy_loop", "count": nak_n})

    # Also surface nak loops even if worker list missed the nick
    for nick, n in nak_counts.items():
        if n >= NAK_BUSY_MIN and not any(s.get("nick", "").lower() == nick for s in stuck):
            findings.append(f"seat {nick} bored nak busy repeated {n} times (>= {NAK_BUSY_MIN})")
            stuck.append({"nick": nick, "reason": "nak_busy_loop", "count": n})

    if perm_count >= 3:
        findings.append(f"PermissionError/WinError5 count={perm_count} in last {LOG_TAIL} chair log lines")

    ok = not findings
    return (
        {
            "ok": ok,
            "busy_seats": [
                {"nick": w.get("nick"), "state": w.get("state"), "working_on": w.get("working_on")}
                for w in workers
            ],
            "accepted_count": len(accepted),
            "stuck": stuck,
            "permission_error_count": perm_count,
            "nak_busy_counts": nak_counts,
            "max_doing_age_sec": DOING_MAX_AGE_SEC,
            "findings": findings,
            "remediation": remediation if findings else [],
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "seats_stuck_doing",
        "Seats stuck doing/offered / NAK busy / PermissionError (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
