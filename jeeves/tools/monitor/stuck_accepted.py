#!/usr/bin/env python3
"""Stuck-accepted-row check: accepted rows older than threshold still not done."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, queue_bucket_rows, resolve_homes, resolve_queue_path, run_check

DEFAULT_MAX_AGE_SEC = 7200  # 2 h
# FR #8384: accepted rows while every live shop seat has blank working_on.
BLANK_WORK_SEC = 600
_PLACEHOLDER_WORK = {"", "working", "offered", "waiting"}


def _age_sec(row: dict) -> float | None:
    for k in ("accepted_ts", "accepted_at", "claimed_at", "ts", "updated", "offered_ts"):
        v = row.get(k)
        if isinstance(v, (int, float)):
            if v > 1_000_000_000_000:
                return time.time() - (v / 1000.0)
            if v > 1_000_000_000:
                return time.time() - float(v)
        if isinstance(v, str) and v:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                return time.time() - dt.timestamp()
            except Exception:
                pass
    return None


def _row_label(row: dict) -> str:
    ident = row.get("id") or row.get("number") or "?"
    repo = row.get("repo") or row.get("owner_repo") or "?"
    return f"{repo}{ident if str(ident).startswith('#') else '#' + str(ident)}"


def _blank_work(row: dict) -> bool:
    text = str(row.get("working_on") or row.get("work") or "").strip().lower()
    return text in _PLACEHOLDER_WORK


def _shop_rows(digest: dict) -> list[dict]:
    out: list[dict] = []
    machines = digest.get("machines") if isinstance(digest.get("machines"), dict) else {}
    for ent in machines.values():
        if not isinstance(ent, dict):
            continue
        for row in ent.get("worker_list") or []:
            if isinstance(row, dict):
                out.append(row)
        workers = ent.get("workers") if isinstance(ent.get("workers"), dict) else {}
        for row in workers.values():
            if isinstance(row, dict):
                out.append(row)
    return out


def _blank_accepted_finding(rows: list[dict], shop_rows: list[dict]) -> str:
    """EXIT-1 text when accepted>0 and no live seat shows a real job (FR #8384)."""
    if not rows:
        return ""
    ages = [a for a in (_age_sec(r) for r in rows) if a is not None]
    if not ages or min(ages) < BLANK_WORK_SEC:
        return ""
    live = [
        r
        for r in shop_rows
        if str(r.get("state") or "").strip().lower() not in ("", "idle")
    ]
    if not live:
        live = list(shop_rows)
    if live and any(not _blank_work(r) for r in live):
        return ""
    return (
        f"accepted={len(rows)} but every live shop seat has empty working_on "
        f"for >{BLANK_WORK_SEC}s"
    )


def _lost_ack_uat0_finding(rows: list[dict], shop_rows: list[dict]) -> str:
    """FR #8525: accepted UAT #0 + LOST_ACK_RESTART while holder digest is idle."""
    hits = []
    by_nick = {
        str(r.get("nick") or "").strip().lower(): r
        for r in shop_rows
        if isinstance(r, dict) and str(r.get("nick") or "").strip()
    }
    for r in rows:
        if not isinstance(r, dict):
            continue
        if str(r.get("task") or "").upper() != "UAT":
            continue
        ident = str(r.get("id") or "").strip().lstrip("#")
        if ident != "0":
            continue
        if str(r.get("reconcile") or "") != "LOST_ACK_RESTART":
            continue
        holder = str(r.get("nick") or r.get("accepted_by") or r.get("offered_to") or "").strip()
        if not holder:
            continue
        shop = by_nick.get(holder.lower())
        state = str((shop or {}).get("state") or "").strip().lower()
        if shop is None or state in ("", "idle", "offered"):
            hits.append(_row_label(r) + f" by {holder}")
    if not hits:
        return ""
    return (
        "stuck accepted UAT #0 LOST_ACK_RESTART with idle digest seat: "
        + "; ".join(hits)
    )


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    stuck = []
    qpath = resolve_queue_path(chair, digest)
    if not qpath.is_file():
        findings.append(f"queue.json missing: {qpath}")
        return ({"ok": False, "findings": findings}, EXIT_FINDING)
    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
    # gitclaim: every row in the accepted bucket is accepted (stamp is ``nick``).
    rows = queue_bucket_rows(queue, "accepted")
    # Also accept legacy shapes that stamp accepted_by on mixed buckets.
    for r in queue_bucket_rows(queue, "rows", "items", "queue"):
        if r.get("accepted_by") or r.get("accepted") or r.get("owner_seat") or r.get("nick"):
            if r not in rows:
                rows.append(r)
    for r in rows:
        if r.get("done"):
            continue
        by = r.get("nick") or r.get("accepted_by") or r.get("owner_seat") or ""
        age = _age_sec(r)
        if age is None:
            stuck.append({"row": _row_label(r), "age_sec": None, "by": by})
            continue
        if age > DEFAULT_MAX_AGE_SEC:
            stuck.append({"row": _row_label(r), "age_sec": int(age), "by": by})
    for s in stuck:
        findings.append(f"stuck accepted {s.get('row')} by {s.get('by')} age_sec={s.get('age_sec')}")
    digest_doc: dict = {}
    dpath = digest / "digest.json"
    if dpath.is_file():
        try:
            digest_doc = json.loads(dpath.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, ValueError):
            digest_doc = {}
    shop = _shop_rows(digest_doc)
    blank = _blank_accepted_finding(rows, shop)
    if blank:
        findings.append(blank)
    lost_uat = _lost_ack_uat0_finding(rows, shop)
    if lost_uat:
        findings.append(lost_uat)
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
