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
# FR #8796: OpenCode progress_phase=stream refreshes last_progress without GitHub
# progress; accepted jobs past this bound with no DONE are a hang finding.
STREAM_HEARTBEAT_MAX_AGE_SEC = DOING_MAX_AGE_SEC
NAK_BUSY_MIN = 3
LOG_TAIL = 400
PERMISSION_RX = re.compile(r"PermissionError|WinError\s*5|Access is denied", re.I)
NAK_BUSY_RX = re.compile(r"bored\s+nak\s+busy", re.I)
WIRE_RX = re.compile(r"\b(ACK|DONE|GIVEUP|NACK)\b", re.I)
DONE_RX = re.compile(r"\bDONE\b", re.I)
STREAM_PHASES = frozenset({"stream", "streaming"})


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


def _nick_key(w: dict) -> str:
    return str(w.get("nick") or w.get("name") or "?").strip().lower()


def _accepted_age_for_nick(accepted: list, nick_l: str) -> float | None:
    """Wall age of the matching accepted row (accepted_ts / offered_ts / ts)."""
    best: float | None = None
    for row in accepted:
        rn = str(row.get("nick") or row.get("accepted_by") or "").strip().lower()
        if not rn or rn != nick_l:
            continue
        age = _age_sec(row.get("accepted_ts") or row.get("offered_ts") or row.get("ts"))
        if age is None:
            continue
        if best is None or age > best:
            best = age
    return best


def _wire_counts(log_lines: list[str], nick_l: str) -> tuple[int, int]:
    """Return (any_wire_hits, done_hits) for lines mentioning nick."""
    wire = 0
    done = 0
    for ln in log_lines:
        if nick_l not in ln.lower():
            continue
        if WIRE_RX.search(ln):
            wire += 1
        if DONE_RX.search(ln):
            done += 1
    return wire, done


def _progress_phase(w: dict) -> str:
    return str(w.get("progress_phase") or w.get("phase") or "").strip().lower()


def _work_text(w: dict) -> str:
    wo = w.get("working_on")
    if isinstance(wo, str) and wo.strip():
        return wo.strip()
    work = w.get("work")
    if isinstance(work, str) and work.strip():
        return work.strip()
    return ""


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
        nick_l = _nick_key(w) if nick != "?" else nick.lower()
        age = None
        # Prefer job-accept age over last_progress / heartbeat clocks (FR #8796).
        # Do not key hang age on last_progress: stream heartbeats refresh it.
        for k in ("state_ts", "doing_ts", "accepted_ts", "offered_ts", "updated", "ts"):
            if k == "last_progress":
                continue
            age = _age_sec(w.get(k))
            if age is not None:
                break
        accepted_age = _accepted_age_for_nick(accepted, nick_l)
        if age is None and accepted_age is not None:
            age = accepted_age
        wire_hits, done_hits = _wire_counts(log_lines, nick_l)
        phase = _progress_phase(w)
        lp_age = _age_sec(w.get("last_progress"))
        work = _work_text(w)

        # Legacy: aged busy with no wire at all (no ACK either).
        if age is not None and age > DOING_MAX_AGE_SEC and wire_hits == 0:
            findings.append(
                f"seat {nick} doing/offered age_sec={int(age)} (>15m) with no ACK/DONE/GIVEUP in recent chair log"
            )
            stuck.append({"nick": nick, "reason": "aged_no_wire", "age_sec": int(age)})

        # FR #8796: accepted doing past bound with no DONE is a hang even when
        # last_progress is fresh (OpenCode stream heartbeats).
        hang_age = accepted_age if accepted_age is not None else age
        if (
            hang_age is not None
            and hang_age > STREAM_HEARTBEAT_MAX_AGE_SEC
            and done_hits == 0
            and str(w.get("state") or "").lower() in ("doing", "busy", "accepted")
        ):
            already = any(
                s.get("nick", "").lower() == nick_l and s.get("reason") in (
                    "aged_no_wire",
                    "stream_heartbeat_no_substantive",
                    "accepted_no_done",
                )
                for s in stuck
            )
            if not already:
                streamish = phase in STREAM_PHASES
                fresh_lp = lp_age is not None and lp_age < STREAM_HEARTBEAT_MAX_AGE_SEC
                if streamish or fresh_lp:
                    reason = "stream_heartbeat_no_substantive" if streamish else "heartbeat_no_done"
                    findings.append(
                        f"seat {nick} doing accepted_age_sec={int(hang_age)} (>15m) "
                        f"progress_phase={phase or '-'} last_progress_age_sec="
                        f"{int(lp_age) if lp_age is not None else 'none'} "
                        f"work={work or '-'} with no DONE (stream/heartbeat is not substantive progress)"
                    )
                    stuck.append(
                        {
                            "nick": nick,
                            "reason": reason,
                            "age_sec": int(hang_age),
                            "progress_phase": phase or "",
                            "last_progress_age_sec": int(lp_age) if lp_age is not None else None,
                            "work": work,
                        }
                    )
                elif accepted_age is not None:
                    findings.append(
                        f"seat {nick} doing accepted_age_sec={int(accepted_age)} (>15m) "
                        f"with no DONE in recent chair log"
                    )
                    stuck.append(
                        {
                            "nick": nick,
                            "reason": "accepted_no_done",
                            "age_sec": int(accepted_age),
                            "work": work,
                        }
                    )

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
            "stream_heartbeat_max_age_sec": STREAM_HEARTBEAT_MAX_AGE_SEC,
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
