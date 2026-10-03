#!/usr/bin/env python3
"""Queue-flow check: unoffered open issues, empty offer queue, rows without pull url."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check


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
    rows = []
    if isinstance(queue, dict):
        for key in ("unaccepted", "accepted", "rows", "items", "queue"):
            v = queue.get(key)
            if isinstance(v, list):
                rows.extend([r for r in v if isinstance(r, dict)])
            elif isinstance(v, dict):
                rows.extend([r for r in v.values() if isinstance(r, dict)])
    offerable = [r for r in rows if not r.get("done") and not r.get("accepted_by") and not r.get("ignored")]
    missing_url = [
        r for r in rows
        if str(r.get("kind") or r.get("type") or "").upper() in ("MRB", "FR")
        and not (r.get("url") or r.get("pull_url") or r.get("pr_url"))
        and not r.get("done")
    ]
    if not offerable and rows:
        # empty offer side while rows exist elsewhere may still be ok; flag only if all done empty
        pass
    if not offerable:
        # soft: report empty offer queue (agent decides whether open GitHub issues exist)
        findings.append("offer queue empty (no unaccepted offerable rows)")
    for r in missing_url[:20]:
        findings.append(
            f"row missing pull url: {r.get('repo') or r.get('owner_repo') or '?'}#{r.get('number') or r.get('id') or '?'}"
        )
    # empty offer alone is informational finding (exit 1) so agent reasons about it
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
