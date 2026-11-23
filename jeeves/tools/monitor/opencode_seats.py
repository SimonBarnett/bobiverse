#!/usr/bin/env python3
"""Live OpenCode seats via GET /bob/v1/report (FR #8583).

Local digest seats_stuck_doing misses remote flamingo OpenCode workers.
This check probes the public report for kind=opencode on selected machines
(default: flamingo), ages ``updated``, flags model_mismatch, and surfaces
opencode-go week/rolling limited windows while seats remain doing/offered.

Report-only: never clear_seat_doing / !assign (harvest #1967).
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from _common import EXIT_FINDING, EXIT_OK, iter_worker_entries, run_check

DEFAULT_REPORT_URL = "https://bob.ntsa.uk/bob/v1/report"
DEFAULT_MACHINES = ("flamingo", "redqueen")
# Issue evidence used ~900s; align with that live stuck threshold.
DEFAULT_STUCK_AGE_SEC = 900
_HTTP_TIMEOUT_S = 30.0
_USER_AGENT = "BobiverseJeevesMonitor-opencode_seats/1.0"


def report_url() -> str:
    return (os.environ.get("BOB_REPORT_URL") or "").strip() or DEFAULT_REPORT_URL


def target_machines() -> tuple[str, ...]:
    raw = (os.environ.get("BOB_OPENCODE_MONITOR_MACHINES") or "").strip()
    if not raw:
        return DEFAULT_MACHINES
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts or DEFAULT_MACHINES


def expect_seats() -> int:
    """FR #9208: configured OpenCode free-seat expectation per shop (default 2)."""
    raw = (os.environ.get("BOB_OPENCODE_EXPECT_SEATS") or "").strip()
    if not raw:
        return 2
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return 2


def stuck_age_sec() -> float:
    raw = (os.environ.get("BOB_OPENCODE_STUCK_AGE_SEC") or "").strip()
    if not raw:
        return float(DEFAULT_STUCK_AGE_SEC)
    try:
        return max(60.0, float(raw))
    except ValueError:
        return float(DEFAULT_STUCK_AGE_SEC)


def _age_sec(stamp: object, *, now: Optional[float] = None) -> float | None:
    now = time.time() if now is None else float(now)
    if isinstance(stamp, (int, float)):
        v = float(stamp)
        if v > 1_000_000_000_000:
            return now - (v / 1000.0)
        if v > 1_000_000_000:
            return now - v
        return None
    if isinstance(stamp, str) and stamp.strip():
        try:
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return now - dt.timestamp()
        except Exception:
            return None
    return None


def _worker_busy(w: dict) -> bool:
    state = str(w.get("state") or "").lower()
    if state in ("doing", "offered", "busy", "accepted"):
        return True
    work = w.get("work") or w.get("working_on")
    if isinstance(work, str):
        return bool(work.strip())
    if isinstance(work, dict):
        return bool(work)
    return bool(work)


def _is_opencode(w: dict) -> bool:
    kind = str(w.get("kind") or "").lower()
    if kind == "opencode":
        return True
    model = str(w.get("start_model") or w.get("model") or w.get("configured_model") or "")
    return model.lower().startswith("opencode") or "/opencode" in model.lower()


def fetch_report(
    url: str,
    *,
    opener: Optional[Callable[..., Any]] = None,
    timeout: float = _HTTP_TIMEOUT_S,
) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    open_fn = opener or urllib.request.urlopen
    with open_fn(req, timeout=timeout) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("report JSON root must be object")
    return data


def load_report_doc(
    *,
    opener: Optional[Callable[..., Any]] = None,
    fixture_path: str = "",
) -> dict[str, Any]:
    fixture = (fixture_path or os.environ.get("BOB_OPENCODE_SEATS_FIXTURE") or "").strip()
    if fixture:
        text = Path(fixture).read_text(encoding="utf-8-sig")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("fixture root must be object")
        return data
    return fetch_report(report_url(), opener=opener)


def opencode_windows(doc: dict[str, Any]) -> dict[str, Any]:
    """Best-effort week/rolling window map from report root."""
    oc = doc.get("opencode")
    if isinstance(oc, dict):
        win = oc.get("windows")
        if isinstance(win, dict):
            return win
    fp = doc.get("fleet_pools")
    if isinstance(fp, dict):
        go = fp.get("opencode-go") or fp.get("opencode_go") or fp.get("opencode")
        if isinstance(go, dict):
            win = go.get("windows")
            if isinstance(win, dict):
                return win
    return {}


def window_limited(win: object) -> bool:
    if not isinstance(win, dict):
        return False
    if win.get("limited") is True:
        return True
    status = str(win.get("status") or "").lower()
    if status in ("exhausted", "limited", "capped"):
        return True
    try:
        rem = win.get("remaining_pct")
        if rem is not None and float(rem) <= 0:
            return True
        used = win.get("used_pct")
        if used is not None and float(used) >= 100:
            return True
    except (TypeError, ValueError):
        pass
    return False


def select_opencode_workers(
    doc: dict[str, Any],
    machines: tuple[str, ...],
) -> list[dict[str, Any]]:
    machines_doc = doc.get("machines")
    if not isinstance(machines_doc, dict):
        return []
    want = {m.lower() for m in machines}
    # Restrict to target machines before iter (iter walks all).
    filtered = {mid: m for mid, m in machines_doc.items() if str(mid).lower() in want}
    out: list[dict[str, Any]] = []
    for w in iter_worker_entries(filtered):
        if _is_opencode(w):
            out.append(w)
    return out


def check(
    args,
    *,
    opener: Optional[Callable[..., Any]] = None,
    now: Optional[float] = None,
) -> tuple[dict[str, Any], int]:
    max_age = stuck_age_sec()
    machines = target_machines()
    doc = load_report_doc(opener=opener)
    workers = select_opencode_workers(doc, machines)
    windows = opencode_windows(doc)
    week = windows.get("week") if isinstance(windows, dict) else None
    rolling = windows.get("rolling") if isinstance(windows, dict) else None
    week_lim = window_limited(week)
    rolling_lim = window_limited(rolling)

    findings: list[str] = []
    seats: list[dict[str, Any]] = []
    stuck: list[dict[str, Any]] = []

    for w in workers:
        nick = str(w.get("nick") or w.get("name") or "?")
        # FR #8795 / #8796: prefer accepted_ts over updated/last_progress (stream heartbeats).
        age = None
        for k in ("accepted_ts", "doing_ts", "offered_ts", "accepted_at"):
            age = _age_sec(w.get(k), now=now)
            if age is not None:
                break
        phase = str(w.get("progress_phase") or w.get("phase") or "").strip().lower()
        heartbeat_only = phase == "stream" or w.get("last_progress") is not None
        if age is None and not heartbeat_only:
            age = _age_sec(w.get("updated") or w.get("updated_at"), now=now)
        elif age is None and heartbeat_only:
            # Still fall back to updated only when no accept stamp exists at all.
            age = _age_sec(w.get("updated") or w.get("updated_at"), now=now)
        busy = _worker_busy(w)
        mismatch = bool(w.get("model_mismatch") or w.get("mismatch"))
        row = {
            "nick": nick,
            "machine": w.get("machine"),
            "state": w.get("state"),
            "kind": w.get("kind"),
            "start_model": w.get("start_model") or w.get("model"),
            "work": w.get("work") or w.get("working_on"),
            "updated": w.get("updated") or w.get("updated_at"),
            "accepted_ts": w.get("accepted_ts") or w.get("accepted_at"),
            "progress_phase": phase or None,
            "last_progress": w.get("last_progress"),
            "age_sec": int(age) if age is not None else None,
            "model_mismatch": mismatch,
            "busy": busy,
        }
        seats.append(row)
        if mismatch:
            findings.append(f"opencode seat {nick} model_mismatch=true")
            stuck.append({**row, "reason": "model_mismatch"})
        if busy and age is not None and age > max_age:
            reason = "stream_heartbeat_stuck_age" if heartbeat_only else "stuck_age"
            findings.append(
                f"opencode seat {nick} state={w.get('state')} accept_age_sec={int(age)} "
                f"(>{int(max_age)}) progress_phase={phase or '-'} work={row.get('work')!r}"
                + (" (stream heartbeat ignored)" if heartbeat_only else "")
            )
            stuck.append({**row, "reason": reason})
        if busy and week_lim:
            reset = week.get("reset_label") if isinstance(week, dict) else None
            findings.append(
                f"opencode seat {nick} still busy while opencode-go week exhausted/limited "
                f"(reset={reset})"
            )
            stuck.append({**row, "reason": "week_exhausted_while_busy"})

    # FR #9208: under-count OpenCode seats per target machine (digest busy rows only).
    expect_n = expect_seats()
    under: list[dict[str, Any]] = []
    if expect_n > 0:
        by_mid: dict[str, int] = {}
        for w in workers:
            mid = str(w.get("machine") or "").strip().lower()
            if not mid:
                nick = str(w.get("nick") or "")
                if "-" in nick:
                    mid = nick.rsplit("-", 1)[0].lower()
            if not mid:
                continue
            by_mid[mid] = by_mid.get(mid, 0) + 1
        for mid in machines:
            m = mid.lower()
            have = int(by_mid.get(m, 0))
            if have < expect_n:
                msg = (
                    f"opencode under-count machine={m} have={have} expect={expect_n} "
                    "(operator TipForm starts seats; monitor never Start-BobWorker)"
                )
                findings.append(msg)
                under.append({"machine": m, "have": have, "expect": expect_n})

    # Dedupe findings text while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for f in findings:
        if f in seen:
            continue
        seen.add(f)
        uniq.append(f)

    remediation = [
        "report only --- never clear_seat_doing / !assign on live working seats (harvest #1967)",
        "intake when flamingo/redqueen OpenCode age exceeds threshold or week window is exhausted while busy",
        "FR #9208: under-count => operator TipForm Agents starts OpenCode seats; do not kill seats from monitor",
        "prefer live GET /bob/v1/report over local digest for remote OpenCode seats",
        "FR #9208: Watch-BobTray Observe seats synthesizes GIVEUP when process gone (park-Watch-only)",
    ]
    payload = {
        "ok": not uniq,
        "machines": list(machines),
        "report_url": report_url() if not (os.environ.get("BOB_OPENCODE_SEATS_FIXTURE") or "").strip() else "fixture",
        "max_age_sec": int(max_age),
        "expect_seats": int(expect_n),
        "opencode_worker_count": len(seats),
        "under_count": under,
        "seats": seats,
        "stuck": stuck,
        "windows": {
            "week": week if isinstance(week, dict) else None,
            "rolling": rolling if isinstance(rolling, dict) else None,
            "week_limited": week_lim,
            "rolling_limited": rolling_lim,
        },
        "findings": uniq,
        "remediation": remediation,
    }
    return payload, EXIT_FINDING if uniq else EXIT_OK


def main(argv: Optional[list[str]] = None) -> int:
    return run_check(
        "opencode_seats",
        "Live flamingo/redqueen OpenCode seats via /bob/v1/report (stuck age, under-count, week quota)",
        check,
        argv=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
