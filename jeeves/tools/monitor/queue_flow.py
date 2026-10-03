#!/usr/bin/env python3
"""Queue-flow check: empty offer queue, MRB rows without pull url."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    queue_bucket_rows,
    resolve_homes,
    row_has_pull_url,
    row_task,
    run_check,
)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    queue = _load_json(chair / "queue.json")
    if queue is None:
        findings.append(f"queue.json missing at {chair}")
        return (
            {"ok": False, "findings": findings, "chair_home": str(chair)},
            EXIT_FINDING,
        )
    unaccepted = queue_bucket_rows(queue, "unaccepted")
    # Offerable = unaccepted rows not needs_human / not ignored.
    offerable = [
        r
        for r in unaccepted
        if not r.get("ignored")
        and not r.get("needs_human")
        and str(r.get("needs_human") or "").lower() not in ("1", "true", "yes")
    ]
    missing_url = [
        r
        for r in unaccepted
        if row_task(r) == "MRB" and not row_has_pull_url(r)
    ]
    if not offerable:
        findings.append("offer queue empty (no unaccepted offerable rows)")
    for r in missing_url[:20]:
        ident = r.get("id") or r.get("number") or "?"
        repo = r.get("repo") or r.get("owner_repo") or "?"
        findings.append(f"row missing pull url: {repo}{ident if str(ident).startswith('#') else '#' + str(ident)}")
    ok = not findings
    return (
        {
            "ok": ok,
            "offerable_count": len(offerable),
            "missing_pull_url_count": len(missing_url),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "queue_flow",
        "Queue flow: empty offer queue / rows without pull url (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
