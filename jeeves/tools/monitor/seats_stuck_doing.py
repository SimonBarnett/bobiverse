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
# FR #8795 / #8796: OpenCode stream heartbeats refresh these; never use them for stuck age.
HEARTBEAT_AGE_KEYS = frozenset(
    {"last_progress", "updated", "updated_at", "ts", "state_ts", "progress_ts"}
)
# Prefer job-accept / doing start stamps over heartbeat fields.
ACCEPT_AGE_KEYS = ("accepted_ts", "doing_ts", "offered_ts")


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


def _is_stream_heartbeat(w: dict) -> bool:
    """True when the seat only shows stream/heartbeat freshness (FR #8795)."""
    phase = _progress_phase(w)
    if phase in STREAM_PHASES:
        return True
    kind = str(w.get("kind") or "").lower()
    if kind == "opencode" and w.get("last_progress") is not None:
        return True
    return False


def _accept_age_sec(w: dict, accepted_rows: list) -> float | None:
    """Age from job-accept stamps only — ignore heartbeat-refreshed fields."""
    nick_l = str(w.get("nick") or w.get("name") or "").lower()
    for k in ACCEPT_AGE_KEYS:
        age = _age_sec(w.get(k))
        if age is not None:
            return age
    for row in accepted_rows:
        rn = str(row.get("nick") or row.get("accepted_by") or "").lower()
        if rn and rn == nick_l:
            for k in ACCEPT_AGE_KEYS:
                age = _age_sec(row.get(k) or row.get("ts"))
                if age is not None:
                    return age
    # Last resort: non-heartbeat stamps only (never last_progress / updated / state_ts).
    for k, v in w.items():
        if str(k).lower() in HEARTBEAT_AGE_KEYS:
            continue
        if str(k).lower().endswith("_ts") or str(k).lower().endswith("_at"):
            age = _age_sec(v)
            if age is not None:
                return age
    return None


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    remediation = [
        "report only by default (keep seats busy; harvest #1967)",
        "restart BobCallback if digest/working_on is stale",
        "clear_seat_doing / idle workers.<pid>.working_on only when accepted is empty AND seat is a true orphan blocking !bored (use --force-orphan-busy)",
        "FR #8795/#8796: OpenCode progress_phase=stream / last_progress heartbeats do not reset accept age — recycle or GIVEUP when accept_age >15m with no DONE (stream/heartbeat is not substantive)",
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
        # FR #8795: age on accepted_ts / doing_ts / offered_ts only — never heartbeat clocks.
        age = _accept_age_sec(w, accepted)
        accepted_age = _accepted_age_for_nick(accepted, nick_l)
        if age is None and accepted_age is not None:
            age = accepted_age
        wire_hits, done_hits = _wire_counts(log_lines, nick_l)
        phase = _progress_phase(w)
        lp_age = _age_sec(w.get("last_progress"))
        work = _work_text(w)

        # Legacy / FR #8795: aged busy with no wire at all (no ACK either).
        if age is not None and age > DOING_MAX_AGE_SEC and wire_hits == 0:
            streamish = _is_stream_heartbeat(w)
            reason = "stream_heartbeat_no_wire" if streamish else "aged_no_wire"
            phase_s = phase or "-"
            findings.append(
                f"seat {nick} doing/offered accept_age_sec={int(age)} (>15m) "
                f"progress_phase={phase_s} with no ACK/DONE/GIVEUP in recent chair log"
                + (" (stream heartbeat ignored)" if streamish else "")
            )
            stuck.append(
                {
                    "nick": nick,
                    "reason": reason,
                    "age_sec": int(age),
                    "progress_phase": phase if phase else None,
                    "kind": w.get("kind"),
                }
            )

        # FR #8796: accepted doing past bound with no DONE is a hang even when
        # last_progress is fresh (OpenCode stream heartbeats) and ACK was seen.
        hang_age = accepted_age if accepted_age is not None else age
        if (
            hang_age is not None
            and hang_age > STREAM_HEARTBEAT_MAX_AGE_SEC
            and done_hits == 0
            and str(w.get("state") or "").lower() in ("doing", "busy", "accepted")
        ):
            already = any(
                s.get("nick", "").lower() == nick_l
                and s.get("reason")
                in (
                    "aged_no_wire",
                    "stream_heartbeat_no_wire",
                    "stream_heartbeat_no_substantive",
                    "heartbeat_no_done",
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
