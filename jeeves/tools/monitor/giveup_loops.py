#!/usr/bin/env python3
"""GIVEUP-loop detector: chair cmd-trace / queue giveup_count hotspots (FR #1622)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    iter_worker_entries,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

GIVEUP_RX = re.compile(r"\bGIVEUP\b", re.I)


def _fold_machine(mid: str) -> str:
    try:
        import bobreport as _br

        return _br.fold_machine_id(mid) or str(mid).strip().lower()
    except Exception:
        return str(mid).strip().lower()


def _live_machine_seat_counts(digest_home: Path) -> dict[str, int]:
    """Folded machine id -> count of worker entries on that machine (digest)."""
    path = digest_home / "digest.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    machines = doc.get("machines") if isinstance(doc, dict) else None
    counts: dict[str, int] = {}
    for w in iter_worker_entries(machines):
        mid = _fold_machine(str(w.get("machine") or ""))
        if not mid:
            continue
        counts[mid] = counts.get(mid, 0) + 1
    return counts


def _row_key(r: dict) -> str:
    return f"{r.get('repo') or r.get('owner_repo') or '?'}#{r.get('number') or r.get('id') or '?'}"


def _require_machine(r: dict) -> str:
    rm = str(r.get("require_machine") or "").strip()
    if rm.lower() in ("*", "any", "none", "-", ""):
        return ""
    return rm


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    notes = []
    counts = {}
    skipped_done = 0
    skipped_gated = 0
    # FR #1622: only active offer/work rows - never historical done[].
    qpath = resolve_queue_path(chair, digest)
    if qpath.is_file():
        try:
            queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
        except Exception:
            queue = None
        # Count done[] high-giveup rows for the note only (must not EXIT 1).
        if isinstance(queue, dict):
            for r in queue_bucket_rows(queue, "done"):
                try:
                    gc = int(r.get("giveup_count") or r.get("giveups") or 0)
                except Exception:
                    gc = 0
                if gc >= 2:
                    skipped_done += 1
            rows = queue_bucket_rows(queue, "unaccepted", "accepted")
        else:
            rows = []
        seat_counts = _live_machine_seat_counts(digest)
        for r in rows:
            try:
                gc = int(r.get("giveup_count") or r.get("giveups") or 0)
            except Exception:
                gc = 0
            if gc < 2:
                continue
            key = _row_key(r)
            rm = _require_machine(r)
            if rm:
                folded = _fold_machine(rm)
                if seat_counts.get(folded, 0) == 0:
                    # Gated pin with no live seats: not a GIVEUP loop (FR #1622 / #1508).
                    skipped_gated += 1
                    notes.append(f"skipped gated giveup_count={gc} on {key} require_machine={rm} (no live seats)")
                    continue
            counts[key] = gc
            findings.append(f"giveup_count={gc} on {key}")
        if skipped_done:
            notes.append(f"ignored {skipped_done} done[] row(s) with giveup_count>=2 (historical)")
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
            "skipped_done_hotspots": skipped_done,
            "skipped_gated_hotspots": skipped_gated,
            "notes": notes,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "giveup_loops",
        "GIVEUP loop / giveup_count hotspot detector (exit 0/1/2; FR #1622 ignores done[])",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
