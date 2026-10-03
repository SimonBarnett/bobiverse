#!/usr/bin/env python3
"""Stale-digest check: digest.json age vs threshold."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check


DEFAULT_MAX_AGE_SEC = 900  # 15 min


def check(args):
    _chair, digest = resolve_homes(args)
    path = digest / "digest.json"
    findings = []
    if not path.is_file():
        findings.append(f"digest.json missing: {path}")
        return ({"ok": False, "findings": findings, "path": str(path)}, EXIT_FINDING)
    age = time.time() - path.stat().st_mtime
    max_age = DEFAULT_MAX_AGE_SEC
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        # optional embedded timestamp
        ts = None
        if isinstance(data, dict):
            ts = data.get("updated") or data.get("ts") or data.get("lastSeen")
        if isinstance(ts, (int, float)) and ts > 1_000_000_000_000:
            age = time.time() - (ts / 1000.0)
        elif isinstance(ts, (int, float)) and ts > 1_000_000_000:
            age = time.time() - float(ts)
    except Exception:
        data = None
    if age > max_age:
        findings.append(f"digest stale age_sec={int(age)} max={max_age}")
    ok = not findings
    return (
        {
            "ok": ok,
            "path": str(path),
            "age_sec": int(age),
            "max_age_sec": max_age,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "stale_digest",
        "Stale digest.json age check (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
