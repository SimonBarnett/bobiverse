#!/usr/bin/env python3
"""Idle-seat detector: digest workers idle while unaccepted queue work exists."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    iter_worker_entries,
    queue_bucket_rows,
    resolve_homes,
    run_check,
)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    dig = _load_json(digest / "digest.json") or {}
    queue = _load_json(chair / "queue.json") or {}
    unaccepted = queue_bucket_rows(queue, "unaccepted")
    idle = []
    machines = dig.get("machines") if isinstance(dig, dict) else None
    for w in iter_worker_entries(machines):
        if str(w.get("state", "")).lower() == "idle":
            idle.append(
                {
                    "machine": w.get("machine"),
                    "nick": w.get("nick") or w.get("name"),
                    "pid": w.get("pid"),
                }
            )
    if idle and unaccepted:
        findings.append(f"{len(idle)} idle seat(s) with {len(unaccepted)} unaccepted row(s)")
    ok = not findings
    return (
        {
            "ok": ok,
            "idle_seats": idle,
            "unaccepted_count": len(unaccepted),
            "digest_path": str(digest / "digest.json"),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "idle_seats",
        "Idle seats vs unaccepted queue work (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
