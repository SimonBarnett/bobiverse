#!/usr/bin/env python3
"""Stuck-accepted-row check: accepted rows older than threshold still not done."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, queue_bucket_rows, resolve_homes, resolve_queue_path, run_check

DEFAULT_MAX_AGE_SEC = 7200  # 2 h


def _age_sec(row: dict) -> float | None:
    for k in ("accepted_ts", "accepted_at", "claimed_at", "ts", "updated", "offered_ts"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            if v > 1_000_000_000_000:
                return time.time() - (v / 1000.0)
            if v > 1_000_000_000:
                return time.time() - float(v)
        if isinstance(v, str) and v:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return time.time() - dt.timestamp()
            except Exception:
                pass
    return None


def _row_label(row: dict) -> str:
    ident = row.get("id") or row.get("number") or "?"
    repo = row.get("repo") or row.get("owner_repo") or "?"
    return f"{repo}{ident if str(ident).startswith('#') else '#' + str(ident)}"


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    stuck = []
    qpath = resolve_queue_path(chair, digest)
    if not qpath.is_file():
        findings.append(f"queue.json missing: {qpath}")
        return ({"ok": False, "findings": findings}, EXIT_FINDING)
    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
    # gitclaim: every row in the accepted bucket is accepted (stamp is ``nick``).
    rows = queue_bucket_rows(queue, "accepted")
    # Also accept legacy shapes that stamp accepted_by on mixed buckets.
    for r in queue_bucket_rows(queue, "rows", "items", "queue"):
        if r.get("accepted_by") or r.get("accepted") or r.get("owner_seat") or r.get("nick"):
            if r not in rows:
                rows.append(r)
    for r in rows:
        if r.get("done"):
            continue
        by = r.get("nick") or r.get("accepted_by") or r.get("owner_seat") or ""
        age = _age_sec(r)
        if age is None:
            stuck.append({"row": _row_label(r), "age_sec": None, "by": by})
            continue
        if age > DEFAULT_MAX_AGE_SEC:
            stuck.append({"row": _row_label(r), "age_sec": int(age), "by": by})
    for s in stuck:
        findings.append(f"stuck accepted {s.get('row')} by {s.get('by')} age_sec={s.get('age_sec')}")
    ok = not findings
    return (
        {
            "ok": ok,
            "stuck": stuck,
            "max_age_sec": DEFAULT_MAX_AGE_SEC,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "stuck_accepted",
        "Stuck accepted queue rows (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
