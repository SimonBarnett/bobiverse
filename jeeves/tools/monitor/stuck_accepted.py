#!/usr/bin/env python3
"""Stuck-accepted-row check: accepted rows older than threshold still not done."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check

DEFAULT_MAX_AGE_SEC = 7200  # 2 h


def _age_sec(row: dict) -> float | None:
    for k in ("accepted_at", "accepted_ts", "claimed_at", "ts", "updated"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            if v > 1_000_000_000_000:
                return time.time() - (v / 1000.0)
            if v > 1_000_000_000:
                return time.time() - float(v)
        if isinstance(v, str) and v:
            # ISO-ish: leave to agent if parse fails
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return time.time() - dt.timestamp()
            except Exception:
                pass
    return None


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    stuck = []
    qpath = chair / "queue.json"
    if not qpath.is_file():
        findings.append(f"queue.json missing: {qpath}")
        return ({"ok": False, "findings": findings}, EXIT_FINDING)
    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
    rows = []
    if isinstance(queue, dict):
        for key in ("accepted", "rows", "items", "queue"):
            v = queue.get(key)
            if isinstance(v, list):
                rows.extend(v)
            elif isinstance(v, dict):
                rows.extend(v.values())
    for r in rows:
        if not isinstance(r, dict):
            continue
        if r.get("done"):
            continue
        if not (r.get("accepted_by") or r.get("accepted") or r.get("owner_seat")):
            continue
        age = _age_sec(r)
        if age is None:
            # accepted without timestamp: still report soft stuck candidate
            stuck.append({"row": r.get("row_key") or r.get("id"), "age_sec": None, "by": r.get("accepted_by")})
            continue
        if age > DEFAULT_MAX_AGE_SEC:
            stuck.append(
                {
                    "row": r.get("row_key") or f"{r.get('repo')}#{r.get('number')}",
                    "age_sec": int(age),
                    "by": r.get("accepted_by"),
                }
            )
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
