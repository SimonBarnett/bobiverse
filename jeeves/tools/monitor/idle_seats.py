#!/usr/bin/env python3
"""Idle-seat detector: digest workers idle while offerable queue work exists (FR #1116)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    iter_worker_entries,
    ops_home,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    run_check,
)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_gitclaim():
    here = Path(__file__).resolve().parent
    candidates = [
        here.parents[1] / "scripts",  # install: <root>/scripts/gitclaim.py
        here.parents[2] / "common" / "scripts",  # repo: common/scripts/gitclaim.py
        here.parents[1] / "common" / "scripts",
    ]
    for cand in candidates:
        if (cand / "gitclaim.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            break
    import gitclaim  # noqa: WPS433

    return gitclaim


def _row_offerable_to_nick(gc, doc, ledger, live: set[str], row: dict, nick: str, now: float) -> bool:
    """Read-only mirror of offer_focus_top eligibility (no offered_to / lock mutation)."""
    me = (gc.canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return False
    if gc.row_needs_human(row, me) or gc.row_on_cooldown(row, now, me):
        return False
    if gc.row_awaits_mrb1(row):
        return False  # FR #1363
    if gc.row_skip_fr_reason(row):
        return False
    if gc.repo_archived_for_queue(str(row.get("repo") or "")):
        return False
    if gc.row_machine_mismatch(row, me) or gc.row_gave_up_by(row, me):
        return False
    if gc.ledger_blocks(ledger, row, me, live):
        return False
    if str(row.get("task") or "").upper() == "FR" and gc.fr_is_superseded(
        doc, str(row.get("repo") or ""), str(row.get("id") or "")
    ):
        return False
    if not gc.fr_row_offerable(row, pr_exists=None):
        return False
    if str(row.get("task") or "").upper() == "UAT" and not gc.is_repo_uat(row):
        return False
    if gc.mrb_already_done(doc, row):
        return False
    if not gc.mrb_row_offerable(row, pr_exists=None):
        return False
    cand_eff = gc.enrich_uat_author_fields(doc, row)
    if gc.review_blocked_for_author(cand_eff, me, live):
        return False
    gc._stamp_require_machine(cand_eff)
    if gc.row_blocked_for_machine(cand_eff, me):
        return False
    return True


def count_offerable_for_live_seats(
    home: Path,
    unaccepted: list[dict],
    idle_nicks: list[str],
    *,
    now: float | None = None,
) -> int:
    """How many unaccepted rows at least one idle nick could take (FR #1116)."""
    if not unaccepted or not idle_nicks:
        return 0
    gc = _ensure_gitclaim()
    now_f = time.time() if now is None else float(now)
    try:
        doc = gc.load_queue(home) if hasattr(gc, "load_queue") else None
    except Exception:
        doc = None
    if not isinstance(doc, dict):
        doc = {"v": 1, "unaccepted": unaccepted, "accepted": [], "done": []}
    else:
        # Prefer the in-memory unaccepted list we already loaded (ops_home resolve).
        doc = dict(doc)
        doc["unaccepted"] = unaccepted
    try:
        ledger = gc.ledger_load(home)
    except Exception:
        ledger = {}
    live = { (gc.canonical_worker_nick(n) or n).strip() for n in idle_nicks if n }
    live |= set(gc.live_seat_nicks(home) or [])
    live = {n for n in live if n}
    n = 0
    for row in unaccepted:
        if any(_row_offerable_to_nick(gc, doc, ledger, live, row, nick, now_f) for nick in idle_nicks):
            n += 1
    return n


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    dig = _load_json(digest / "digest.json") or {}
    qpath = resolve_queue_path(chair, digest)
    queue = _load_json(qpath) or {}
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
    idle_nicks = [str(x.get("nick") or "") for x in idle if x.get("nick")]
    home = ops_home(chair, digest)
    # Prefer digest home when queue lives there (gitclaim lock/ledger).
    if qpath.parent != home:
        home = qpath.parent
    offerable = count_offerable_for_live_seats(home, unaccepted, idle_nicks)
    if idle and offerable > 0:
        findings.append(
            f"{len(idle)} idle seat(s) with {offerable} offerable row(s) "
            f"(unaccepted={len(unaccepted)})"
        )
    ok = not findings
    return (
        {
            "ok": ok,
            "idle_seats": idle,
            "unaccepted_count": len(unaccepted),
            "offerable_for_live_seats": offerable,
            "digest_path": str(digest / "digest.json"),
            "queue_path": str(qpath),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "idle_seats",
        "Idle seats vs offerable queue work for live seats (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())