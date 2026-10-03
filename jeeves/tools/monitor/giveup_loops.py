#!/usr/bin/env python3
"""GIVEUP-loop detector: chair cmd-trace / queue giveup_count hotspots."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, resolve_queue_path, run_check

GIVEUP_RX = re.compile(r"\bGIVEUP\b", re.I)


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    counts = {}
    # queue giveup_count fields
    qpath = resolve_queue_path(chair, digest)
    if qpath.is_file():
        try:
            queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
        except Exception:
            queue = None
        rows = []
        if isinstance(queue, dict):
            for key in ("unaccepted", "accepted", "rows", "items", "queue", "done"):
                v = queue.get(key)
                if isinstance(v, list):
                    rows.extend(v)
                elif isinstance(v, dict):
                    rows.extend(v.values())
        for r in rows:
            if not isinstance(r, dict):
                continue
            gc = r.get("giveup_count") or r.get("giveups") or 0
            try:
                gc = int(gc)
            except Exception:
                gc = 0
            if gc >= 2:
                key = f"{r.get('repo') or r.get('owner_repo') or '?'}#{r.get('number') or r.get('id') or '?'}"
                counts[key] = gc
                findings.append(f"giveup_count={gc} on {key}")
    # recent cmd-trace lines
    trace = chair / "cmd-trace.log"
    recent_giveups = 0
    if trace.is_file():
        try:
            lines = trace.read_text(encoding="utf-8-sig", errors="replace").splitlines()[-200:]
            recent_giveups = sum(1 for ln in lines if GIVEUP_RX.search(ln))
            if recent_giveups >= 5:
                findings.append(f"cmd-trace has {recent_giveups} GIVEUP lines in last 200")
        except Exception:
            pass
    ok = not findings
    return (
        {
            "ok": ok,
            "hotspots": counts,
            "recent_giveup_lines": recent_giveups,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "giveup_loops",
        "GIVEUP loop / giveup_count hotspot detector (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
