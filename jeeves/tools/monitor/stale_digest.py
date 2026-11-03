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
        ts = None
        if isinstance(data, dict):
            ts = data.get("updated") or data.get("ts") or data.get("lastSeen")
        if isinstance(ts, (int, float)) and ts > 1_000_000_000_000:
            age = time.time() - (ts / 1000.0)
        elif isinstance(ts, (int, float)) and ts > 1_000_000_000:
            age = time.time() - float(ts)
        elif isinstance(ts, str) and ts.strip():
            # FR #6100: digest.ts is ISO-8601 (…Z). File mtime can be fresh while ts is frozen.
            from datetime import datetime, timezone

            raw = ts.strip()
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age = time.time() - parsed.timestamp()
            machines = data.get("machines") if isinstance(data.get("machines"), dict) else {}
            seen_ages = []
            for ent in machines.values():
                if not isinstance(ent, dict):
                    continue
                ls = str(ent.get("lastSeen") or "").strip()
                if not ls:
                    continue
                if ls.endswith("Z"):
                    ls = ls[:-1] + "+00:00"
                try:
                    seen = datetime.fromisoformat(ls)
                except ValueError:
                    continue
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=timezone.utc)
                seen_ages.append(time.time() - seen.timestamp())
            if seen_ages and min(seen_ages) > max_age:
                age = max(age, min(seen_ages))
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
