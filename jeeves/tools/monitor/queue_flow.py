#!/usr/bin/env python3
"""Queue-flow check: empty offer queue, MRB rows without pull url."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    ops_home,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    row_has_pull_url,
    row_task,
    run_check,
)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    qpath = resolve_queue_path(chair, digest)
    ops = ops_home(chair, digest)
    queue = _load_json(qpath)
    if queue is None:
        findings.append(f"queue.json missing at {ops} (chair={chair} digest={digest})")
        return (
            {"ok": False, "findings": findings, "chair_home": str(chair)},
            EXIT_FINDING,
        )
    unaccepted = queue_bucket_rows(queue, "unaccepted")
    # FR #1116: prefer gitclaim gates when available; else needs_human/ignored only.
    offerable = []
    try:
        import idle_seats as _idle

        # Without digest idle nicks, treat "offerable" as rows any registered seat
        # could theoretically take via the same gates (empty idle list → 0).
        # queue_flow only needs a non-empty offerable set for "work exists".
        dig = _load_json(digest / "digest.json") or {}
        from _common import iter_worker_entries

        nicks = []
        machines = dig.get("machines") if isinstance(dig, dict) else None
        for w in iter_worker_entries(machines):
            nick = w.get("nick") or w.get("name")
            if nick:
                nicks.append(str(nick))
        if not nicks:
            # Fallback: coarse filter when digest has no workers yet.
            offerable = [
                r
                for r in unaccepted
                if not r.get("ignored")
                and not r.get("needs_human")
                and str(r.get("needs_human") or "").lower() not in ("1", "true", "yes")
            ]
        else:
            home = qpath.parent
            n = _idle.count_offerable_for_live_seats(home, unaccepted, nicks)
            # Materialize placeholder list for count compatibility.
            offerable = list(range(n))
    except Exception:
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
        # FR #1508: distinguish gated-empty (pins / no seats) from true empty.
        pin_rows = []
        for r in unaccepted:
            rm = str(r.get("require_machine") or "").strip()
            if rm and rm.lower() not in ("*", "any", "none", "-"):
                pin_rows.append(r)
        live_unacc = [r for r in unaccepted if not r.get("ignored")]
        if pin_rows and len(pin_rows) == len(live_unacc):
            # Fold hosting labels (ionos→win-mpre8vi4u6u, dev1→ce-priority-dev1)
            # so zero-seat detection matches digest machine keys (FR #1508 / #79).
            try:
                import bobreport as _br

                def _fold(mid: str) -> str:
                    return _br.fold_machine_id(mid) or str(mid).strip().lower()
            except Exception:
                def _fold(mid: str) -> str:
                    return str(mid).strip().lower()

            machines: dict[str, int] = {}
            dig = _load_json(digest / "digest.json") or {}
            for mid, ent in ((dig.get("machines") or {}) if isinstance(dig, dict) else {}).items():
                wl = (ent or {}).get("worker_list") if isinstance(ent, dict) else None
                n = len(wl) if isinstance(wl, list) else 0
                key = _fold(str(mid))
                machines[key] = machines.get(key, 0) + n
            missing = sorted({
                _fold(str(r.get("require_machine") or ""))
                for r in pin_rows
                if machines.get(_fold(str(r.get("require_machine") or "")), 0) == 0
            } - {""})
            if missing:
                findings.append(
                    "offer queue gated: require_machine pins only; no seats on "
                    + ",".join(missing)
                )
            else:
                findings.append(
                    "offer queue gated: require_machine pins only (seats present on pin machines)"
                )
        else:
            findings.append("offer queue empty (no unaccepted offerable rows)")
    for r in missing_url[:20]:
        ident = r.get("id") or r.get("number") or "?"
        repo = r.get("repo") or r.get("owner_repo") or "?"
        findings.append(f"row missing pull url: {repo}{ident if str(ident).startswith('#') else '#' + str(ident)}")
    ok = not findings
    return (
        {
            "ok": ok,
            "ops_home": str(ops),
            "queue_path": str(qpath),
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
