#!/usr/bin/env python3
"""FR #9145: token-free check for orphan workers_last_good when live workers are empty."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, resolve_homes, run_check


def _parse_iso(raw: object) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        parsed = datetime.fromisoformat(s)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_s(raw: object, now: datetime) -> float | None:
    parsed = _parse_iso(raw)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def _workers_last_good_max_s() -> float:
    try:
        import bobreport

        return float(bobreport.workers_last_good_max_s())
    except Exception:
        import os

        raw = (os.environ.get("BOB_DIGEST_LAST_GOOD_MAX_S") or "").strip()
        if not raw:
            return 1800.0
        try:
            return max(60.0, float(raw))
        except ValueError:
            return 1800.0


def _coerce_list(raw: object) -> list:
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def check(args):
    _chair, digest = resolve_homes(args)
    path = digest / "digest.json"
    now = datetime.now(timezone.utc)
    ttl = _workers_last_good_max_s()

    if not path.is_file():
        return (
            {
                "ok": True,
                "digest_present": False,
                "path": str(path),
                "findings": [],
                "orphans": [],
                "remediation": "",
            },
            EXIT_OK,
        )

    try:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except Exception as e:
        return (
            {
                "ok": False,
                "digest_present": True,
                "path": str(path),
                "error": f"{type(e).__name__}: {e}",
                "findings": [f"digest unreadable: {e}"],
                "orphans": [],
            },
            EXIT_ERROR,
        )

    if not isinstance(data, dict):
        return (
            {
                "ok": False,
                "digest_present": True,
                "path": str(path),
                "error": "digest root is not an object",
                "findings": ["digest root is not an object"],
                "orphans": [],
            },
            EXIT_ERROR,
        )

    machines = data.get("machines")
    if machines is None:
        machines = {}
    if not isinstance(machines, dict):
        return (
            {
                "ok": False,
                "digest_present": True,
                "path": str(path),
                "error": "machines is not an object",
                "findings": ["machines is not an object"],
                "orphans": [],
            },
            EXIT_ERROR,
        )

    findings: list[str] = []
    orphans: list[dict] = []
    for mid, ent in machines.items():
        if not isinstance(ent, dict):
            continue
        if not ent.get("workers_stale"):
            continue
        workers_map = ent.get("workers")
        if isinstance(workers_map, dict) and any(workers_map.values()):
            continue
        live = _coerce_list(ent.get("worker_list"))
        if live:
            continue
        last = _coerce_list(ent.get("workers_last_good"))
        if not last:
            continue
        nicks = [str(r.get("nick") or "").strip() for r in last if str(r.get("nick") or "").strip()]
        states = [str(r.get("state") or "").strip() for r in last]
        at = ent.get("workers_last_good_at")
        age = _age_s(at, now)
        age_over = True if age is None else (float(age) > ttl)
        orphans.append(
            {
                "machine": str(mid),
                "nicks": nicks,
                "states": states,
                "workers_last_good_at": at,
                "age_s": None if age is None else int(age),
                "age_over_ttl": age_over,
                "ttl_s": int(ttl),
            }
        )
        findings.append(
            f"workers_last_good orphan machine={mid} nicks={','.join(nicks) or '-'} "
            f"stale=1 live_empty=1 age_over_ttl={int(age_over)}"
        )

    remediation = ""
    if orphans:
        hints = []
        for o in orphans:
            for nick in o.get("nicks") or []:
                hints.append(f"worker-remove machine={o['machine']} nick={nick}")
        remediation = (
            "Send POST /bob/v1/report worker-remove for each nick (or delete-worker by pid); "
            + "; ".join(hints[:12])
        )

    ok = not findings
    return (
        {
            "ok": ok,
            "digest_present": True,
            "path": str(path),
            "findings": findings,
            "orphans": orphans,
            "remediation": remediation,
            "ttl_s": int(ttl),
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "workers_last_good_orphan",
        "Orphan workers_last_good when live workers empty (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
