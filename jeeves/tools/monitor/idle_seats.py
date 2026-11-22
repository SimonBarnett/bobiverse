#!/usr/bin/env python3
"""Idle-seat detector: digest workers idle while offerable queue work exists (FR #1116 / #1625 / #8536).

FR #8536: when idle seats exist and offerable==0, emit healthy_idle_empty_offerable
(+ queue_needs_human_only when every unaccepted row is needs_human) so ops do not
recycle free DeepSeek seats as hung.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
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

# Full shop nick: {machine}-{pid}. Short w-mh-* / w-io-* digest ghosts are not starve seats (FR #1625).
_SHOP_NICK_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]*-\d+$", re.I)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_gitclaim():
    from _common import ensure_script_dir_on_path

    # FR #8580: no parents[N]; walk upward for gitclaim.py
    ensure_script_dir_on_path("gitclaim.py")
    import gitclaim  # noqa: WPS433

    return gitclaim


def is_starve_idle_nick(nick: str) -> bool:
    """True when digest nick is a real shop seat for starve math (FR #1625).

    Drops ``w-mh-*`` / ``w-io-*`` short ghosts and anything that is not ``machine-pid``.
    """
    n = (nick or "").strip()
    if not n or n.lower().startswith("w-") or n.lower().startswith("bob-"):
        return False
    return bool(_SHOP_NICK_RX.match(n))


def row_offer_pending(row: dict, *, now: float | None = None, timeout_s: float | None = None) -> bool:
    """True when ``offered_to`` is still within assign grace (awaiting ACK; FR #1625)."""
    to = str(row.get("offered_to") or "").strip()
    if not to:
        return False
    try:
        import gitclaim as gc

        limit = float(gc.OFFER_TIMEOUT_S if timeout_s is None else timeout_s)
    except Exception:
        limit = float(90.0 if timeout_s is None else timeout_s)
    now_f = time.time() if now is None else float(now)
    try:
        age = now_f - datetime.fromisoformat(
            str(row.get("offered_ts") or "").replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        age = limit + 1
    return age < limit


def collect_idle_shop_seats(machines: object) -> list[dict]:
    """Idle digest workers, deduped by canonical nick, shop-form only (FR #1625)."""
    try:
        gc = _ensure_gitclaim()
    except Exception:
        gc = None
    seen: set[str] = set()
    out: list[dict] = []
    for w in iter_worker_entries(machines):
        if str(w.get("state") or "").lower() != "idle":
            continue
        nick = str(w.get("nick") or w.get("name") or "").strip()
        if not is_starve_idle_nick(nick):
            continue
        key = nick.lower()
        if gc is not None:
            try:
                key = (gc.canonical_worker_nick(nick) or nick).strip().lower()
            except Exception:
                key = nick.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "machine": w.get("machine"),
                "nick": nick,
                "pid": w.get("pid"),
            }
        )
    return out


def _row_offerable_to_nick(gc, doc, ledger, live: set[str], row: dict, nick: str, now: float, home=None) -> bool:
    """Read-only mirror of offer_focus_top eligibility (no offered_to / lock mutation)."""
    me = (gc.canonical_worker_nick(nick) or nick or "").strip()
    if not me:
        return False
    # FR #1625: row already offered to a seat awaiting ACK — not starve offerable.
    if row_offer_pending(row, now=now):
        return False
    if gc.row_needs_human(row, me) or gc.row_on_cooldown(row, now, me):
        return False
    # row_awaits_mrb1 is always False (needs-mrb1 hallucination; keep call for API parity)
    if gc.row_awaits_mrb1(row):
        return False
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
    # FR #5900: MRB must use enrich_review_author_fields (exact-seat). UAT enrich
    # on an MRB row can mis-apply sibling stamps and hide eligible same-machine seats.
    cand_eff = gc.enrich_review_author_fields(doc, row)
    if gc.review_blocked_for_author(cand_eff, me, live):
        return False
    gc._stamp_require_machine(cand_eff)
    if gc.row_blocked_for_machine(cand_eff, me):
        return False
    # FR #6134: OpenCode seats skip MRB/UAT (mirror offer_focus_top).
    if home is not None and hasattr(gc, "row_blocked_for_opencode_seat"):
        if gc.row_blocked_for_opencode_seat(cand_eff, me, home):
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
    # Match !bored: focus.strict drops unfocused repos (plan-smoke vs bobiverse focus).
    try:
        import focus_ignore

        rows = focus_ignore.sort_unaccepted_rows(home, list(unaccepted))
    except Exception:
        rows = list(unaccepted)
    n = 0
    for row in rows:
        if any(_row_offerable_to_nick(gc, doc, ledger, live, row, nick, now_f, home) for nick in idle_nicks):
            n += 1
    return n


def collect_under_cap(dig: dict, offerable: int, default_cap: int = 2) -> list:
    """FR #8890: online machines with a known worker list below cap while work is offerable."""
    if offerable < 1 or not isinstance(dig, dict):
        return []
    machines = dig.get("machines") or {}
    if not isinstance(machines, dict):
        return []
    found = []
    for mid, ent in machines.items():
        if not isinstance(ent, dict) or not ent.get("online"):
            continue
        if "workers" not in ent:
            continue
        raw = ent.get("workers")
        if isinstance(raw, dict):
            rows = [v for v in raw.values() if isinstance(v, dict)]
        elif isinstance(raw, list):
            rows = [v for v in raw if isinstance(v, dict)]
        else:
            continue
        cap = ent.get("seat_cap", ent.get("worker_cap", default_cap))
        try:
            cap_n = int(cap)
        except (TypeError, ValueError):
            cap_n = default_cap
        if cap_n < 1 or len(rows) >= cap_n:
            continue
        found.append({"machine": str(mid), "live": len(rows), "cap": cap_n})
    return found


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    notes = []
    dig = _load_json(digest / "digest.json") or {}
    qpath = resolve_queue_path(chair, digest)
    queue = _load_json(qpath) or {}
    unaccepted = queue_bucket_rows(queue, "unaccepted")
    machines = dig.get("machines") if isinstance(dig, dict) else None
    idle = collect_idle_shop_seats(machines)
    pending_offers = sum(1 for r in unaccepted if isinstance(r, dict) and row_offer_pending(r))
    if pending_offers:
        notes.append(
            f"{pending_offers} unaccepted row(s) offered_to awaiting ACK (not starve offerable; FR #1625)"
        )
    idle_nicks = [str(x.get("nick") or "") for x in idle if x.get("nick")]
    home = ops_home(chair, digest)
    # Prefer digest home when queue lives there (gitclaim lock/ledger).
    if qpath.parent != home:
        home = qpath.parent
    offerable = count_offerable_for_live_seats(home, unaccepted, idle_nicks)
    queue_doc = dig.get("queue") if isinstance(dig, dict) and isinstance(dig.get("queue"), dict) else {}
    try:
        fleet_offerable = int(queue_doc.get("offerable_count") or 0)
    except (TypeError, ValueError):
        fleet_offerable = 0
    under_cap = collect_under_cap(dig if isinstance(dig, dict) else {}, fleet_offerable)
    for row in under_cap:
        findings.append(
            f"under-cap {row['machine']} live={row['live']}/{row['cap']} "
            f"offerable={fleet_offerable}"
        )
    if idle and offerable > 0:
        findings.append(
            f"{len(idle)} idle seat(s) with {offerable} offerable row(s) "
            f"(unaccepted={len(unaccepted)})"
        )
    # FR #8536: distinguish healthy idle + empty offerable queue from hung seats.
    healthy_idle = bool(idle) and offerable == 0
    needs_human_only = False
    if unaccepted:
        try:
            gc = _ensure_gitclaim()
            needs_human_only = all(
                isinstance(r, dict) and gc.row_needs_human(r, "") for r in unaccepted
            )
        except Exception:
            needs_human_only = all(
                isinstance(r, dict) and bool(r.get("needs_human")) for r in unaccepted
            )
    if healthy_idle:
        reason = "needs_human-only" if needs_human_only else "gated/empty offerable"
        notes.append(
            f"{len(idle)} idle seat(s) healthy with 0 offerable "
            f"(unaccepted={len(unaccepted)}; {reason}; do not recycle as hung)"
        )
    ok = not findings
    return (
        {
            "ok": ok,
            "idle_seats": idle,
            "unaccepted_count": len(unaccepted),
            "offerable_for_live_seats": offerable,
            "fleet_offerable_count": fleet_offerable,
            "under_cap": under_cap,
            "pending_offer_count": pending_offers,
            "healthy_idle_empty_offerable": healthy_idle,
            "queue_needs_human_only": bool(needs_human_only),
            "notes": notes,
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