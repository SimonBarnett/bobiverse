#!/usr/bin/env python3
"""Idle-seat detector: digest workers idle while offerable queue work exists (FR #1116 / #1625 / #8536 / #9461).

FR #9461: EXIT 1 idle+offerable triggers ear-relay !assign by default (--no-intervene to report-only).

FR #8536: when idle seats exist and offerable==0, emit healthy_idle_empty_offerable
(+ queue_needs_human_only when every unaccepted row is needs_human) so ops do not
recycle free DeepSeek seats as hung.
"""
from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from _common import (
    EXIT_ERROR,
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
    # FR #9478: pass free= so soft MRB machine-id matches !bored (busy other-machine
    # does not strand same-machine idle seats).
    free = None
    if home is not None:
        try:
            free = gc.free_seat_nicks(home, live)
        except Exception:
            free = None
    if gc.review_blocked_for_author(cand_eff, me, live, free=free):
        return False
    gc._stamp_require_machine(cand_eff)
    if gc.row_blocked_for_machine(cand_eff, me):
        return False
    # FR #6134: OpenCode seats skip MRB/UAT (mirror offer_focus_top).
    if home is not None and hasattr(gc, "row_blocked_for_opencode_seat"):
        if gc.row_blocked_for_opencode_seat(cand_eff, me, home):
            return False
    # FR #9553 / #9455: Depends-on gate shared with !assign / !stuck / offerable_count.
    if str(row.get("task") or "").upper() == "FR":
        try:
            open_keys = gc.open_fr_issue_keys(doc) if isinstance(doc, dict) else set()
        except Exception:
            open_keys = set()
        if gc.depends_gate_reason(cand_eff, doc if isinstance(doc, dict) else None, open_keys=open_keys):
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


# FR #8866: report-only estimate. These gates need chair files and are not applied.
_UNVERIFIED_GATES = (
    "focus",
    "ignore",
    "ledger",
    "review-author",
    "fr-mrb-shape",
    "free-fuel",
    "inferred-pins",
)


def _explicit_pin(row: dict) -> str:
    return str(row.get("require_machine") or "").strip()


def estimate_offerable_from_report(
    rows: list,
    idle_seats: list[dict],
    now: float,
) -> int | None:
    """Rows a live idle seat could take using only fields on the public report.

    Returns None when there are no idle seats (caller should not treat that as
    a counted zero from row gates). Does not read or write the local home.
    """
    if not idle_seats:
        return None
    gc = None
    try:
        gc = _ensure_gitclaim()
    except Exception:
        gc = None
    machines = {
        str(s.get("machine") or "").strip().lower()
        for s in idle_seats
        if str(s.get("machine") or "").strip()
    }
    nicks = [str(s.get("nick") or "") for s in idle_seats if str(s.get("nick") or "").strip()]
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row_offer_pending(row, now=now):
            continue
        taken = False
        for nick in nicks:
            if gc is not None:
                if gc.row_needs_human(row, nick) or gc.row_on_cooldown(row, now, nick):
                    continue
            elif row.get("needs_human"):
                continue
            pin = _explicit_pin(row)
            if pin and pin.lower() not in machines:
                continue
            taken = True
            break
        if taken:
            n += 1
    return n


def _drop_stale_worker_machines(machines: dict) -> tuple[dict, list[str]]:
    kept = {}
    dropped = []
    for mid, m in machines.items():
        if isinstance(m, dict) and m.get("workers_stale"):
            dropped.append(str(mid))
            continue
        kept[mid] = m
    return kept, dropped


def _live_report_unusable(doc, overlay) -> bool:
    if doc is None or overlay is None:
        return True
    if doc.get("stale") is True:
        return True
    if not isinstance(doc.get("machines"), dict):
        return True
    queue = doc.get("queue")
    if not isinstance(queue, dict) or not isinstance(queue.get("unaccepted"), list):
        return True
    return False


def _check_live_report(chair, digest, qpath, *, require_missing_queue: bool = True, report=None):
    """FR #8866 / #9557: prefer one live /report when local queue is missing or stale."""
    import _common as common

    findings = []
    notes = []
    doc = report if isinstance(report, dict) else common.fetch_live_report()
    overlay = common.non_chair_overlay(
        chair,
        digest,
        require_missing_queue=require_missing_queue,
        report=doc,
        fetch=False,
    )
    # FR #9557: when local queue exists but is stale, overlay may be None under
    # require_missing_queue — still accept a fresh structured report.
    usable_overlay = overlay if overlay is not None else (
        {"non_chair_overlay": True, "stale_local_bypass": True}
        if (not require_missing_queue and doc is not None and common.live_report_is_fresh(doc))
        else None
    )
    url = common.live_report_url()
    if _live_report_unusable(doc, usable_overlay):
        findings.append("local queue missing; live report unavailable/stale/incomplete")
        return (
            {
                "ok": False,
                "idle_seats": [],
                "unaccepted_count": 0,
                "offerable_for_live_seats": 0,
                "pending_offer_count": 0,
                "healthy_idle_empty_offerable": False,
                "queue_needs_human_only": False,
                "notes": notes,
                "digest_path": str(digest / "digest.json"),
                "queue_path": str(qpath),
                "findings": findings,
                "source": "live_report",
                "live_report_url": url,
                "offerable_estimate": True,
                "unverified_gates": list(_UNVERIFIED_GATES),
            },
            EXIT_FINDING,
        )
    overlay = usable_overlay
    queue = doc["queue"]
    rows = [r for r in queue["unaccepted"] if isinstance(r, dict)]
    machines, dropped = _drop_stale_worker_machines(doc["machines"])
    if dropped:
        notes.append("skipped workers_stale machines: " + ", ".join(dropped))
    idle = collect_idle_shop_seats(machines)
    now = time.time()
    pending_offers = sum(1 for r in rows if row_offer_pending(r, now=now))
    if pending_offers:
        notes.append(
            f"{pending_offers} unaccepted row(s) offered_to awaiting ACK (not starve offerable; FR #1625)"
        )
    offerable = estimate_offerable_from_report(rows, idle, now)
    if offerable is None:
        offerable = 0
    if idle and offerable > 0:
        named = ", ".join(str(x.get("nick") or "") for x in idle if x.get("nick"))
        findings.append(
            f"idle seat {named} with {offerable} offerable unaccepted row(s) (live report)"
        )
    healthy_idle = bool(idle) and offerable == 0
    needs_human_only = False
    if rows:
        try:
            gc = _ensure_gitclaim()
            needs_human_only = all(gc.row_needs_human(r, "") for r in rows)
        except Exception:
            needs_human_only = all(bool(r.get("needs_human")) for r in rows)
    if healthy_idle:
        reason = "needs_human-only" if needs_human_only else "gated/empty offerable"
        notes.append(
            f"{len(idle)} idle seat(s) healthy with 0 offerable "
            f"(unaccepted={len(rows)}; {reason}; live-report estimate)"
        )
    else:
        notes.append("live-report estimate (FR #8866); unverified gates not applied")
    ok = not findings
    payload = {
        "ok": ok,
        "idle_seats": idle,
        "unaccepted_count": len(rows),
        "offerable_for_live_seats": int(offerable),
        "pending_offer_count": pending_offers,
        "healthy_idle_empty_offerable": healthy_idle,
        "queue_needs_human_only": bool(needs_human_only),
        "notes": notes,
        "digest_path": str(digest / "digest.json"),
        "queue_path": str(qpath),
        "findings": findings,
        "source": "live_report",
        "offerable_estimate": True,
        "unverified_gates": list(_UNVERIFIED_GATES),
        "report_offerable_count": queue.get("offerable_count"),
    }
    if isinstance(overlay, dict):
        payload.update(overlay)
    return (payload, EXIT_OK if ok else EXIT_FINDING)


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
    import _common as common

    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    # FR #8866: missing local queue is the non-chair case (same resolver as queue_flow).
    if not qpath.is_file():
        return _check_live_report(chair, digest, qpath)
    # FR #9557: present but empty/stale local home (typical non-chair ~/.jeeves)
    # must not paint false idle/starve vs the live walrus digest.
    live_doc = None
    with contextlib.suppress(Exception):
        live_doc = common.fetch_live_report()
    stale_why = ""
    with contextlib.suppress(Exception):
        stale_why = common.local_ops_stale_vs_live_report(chair, digest, live_doc) or ""
    if stale_why:
        # Prefer live report for seats when usable; else soft-skip EXIT 0 (no false starve).
        probe_overlay = (
            {"non_chair_overlay": True}
            if (live_doc is not None and common.live_report_is_fresh(live_doc))
            else None
        )
        if not _live_report_unusable(live_doc, probe_overlay):
            payload, code = _check_live_report(
                chair,
                digest,
                qpath,
                require_missing_queue=False,
                report=live_doc,
            )
            payload["stale_local_home"] = stale_why
            payload["source"] = "live_report_stale_local"
            notes = list(payload.get("notes") or [])
            notes.append(
                f"stale_local_home={stale_why}; preferred live /bob/v1/report for seats (FR #9557)"
            )
            payload["notes"] = notes
            return payload, code
        return (
            {
                "ok": True,
                "skipped": "stale_local_home",
                "stale_local_home": stale_why,
                "idle_seats": [],
                "unaccepted_count": 0,
                "offerable_for_live_seats": 0,
                "pending_offer_count": 0,
                "healthy_idle_empty_offerable": False,
                "queue_needs_human_only": False,
                "notes": [
                    f"skipped=stale_local_home ({stale_why}); "
                    "local ops empty/stale and live report unusable (FR #9557)"
                ],
                "digest_path": str(digest / "digest.json"),
                "queue_path": str(qpath),
                "findings": [],
                "source": "skipped_stale_local",
            },
            EXIT_OK,
        )
    findings = []
    notes = []
    dig = _load_json(digest / "digest.json") or {}
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
    """FR #9461: optional ear-relay intervene when EXIT 1 (idle+offerable)."""
    import argparse

    from _common import emit

    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(
        prog="idle_seats",
        description=(
            "Idle seats vs offerable queue work for live seats (exit 0/1/2); "
            "optional ear-relay !assign intervene (FR #9461)"
        ),
    )
    p.add_argument("--help-exit0", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--dry-run", action="store_true", help="offline: emit ok JSON and exit 0")
    p.add_argument("--chair-home", default="", help="override ~/.jeeves")
    p.add_argument("--digest-home", default="", help="override ~/.bobiverse")
    # FR #9461: default intervene ON so Start-JeevesMonitor keeps fleet moving.
    p.add_argument(
        "--intervene",
        dest="intervene",
        action="store_true",
        default=True,
        help="on EXIT 1 idle+offerable, ear-relay !assign (default on)",
    )
    p.add_argument(
        "--no-intervene",
        dest="intervene",
        action="store_false",
        help="report-only (legacy)",
    )
    p.add_argument(
        "--intervene-dry-run",
        action="store_true",
        help="plan !assign lines without writing ear outbox",
    )
    p.add_argument("--ear-outbox", default="", help="ear outbox.txt for intervene")
    p.add_argument(
        "--force-needs-human",
        action="store_true",
        help="intervene may pick needs_human rows",
    )
    p.add_argument("--pace-s", type=float, default=3.0, help="pace between !assign lines")
    p.add_argument(
        "--truncate-outbox",
        action="store_true",
        help="truncate drained ear outbox after intervene",
    )
    args = p.parse_args(argv)
    if args.help_exit0:
        p.print_help()
        return EXIT_OK
    if args.dry_run:
        return emit(
            {
                "check": "idle_seats",
                "ok": True,
                "dry_run": True,
                "findings": [],
                "intervene": False,
            },
            EXIT_OK,
        )
    try:
        payload, code = check(args)
    except Exception as e:
        return emit(
            {
                "check": "idle_seats",
                "ok": False,
                "dry_run": False,
                "error": f"{type(e).__name__}: {e}",
                "findings": [str(e)],
            },
            EXIT_ERROR,
        )
    payload.setdefault("check", "idle_seats")
    payload.setdefault("dry_run", False)
    payload["intervene_requested"] = bool(getattr(args, "intervene", True))
    try:
        offerable = int(payload.get("offerable_for_live_seats") or 0)
    except (TypeError, ValueError):
        offerable = 0
    idle_n = len(payload.get("idle_seats") or [])
    should = (
        bool(getattr(args, "intervene", True))
        and code == EXIT_FINDING
        and idle_n > 0
        and offerable > 0
    )
    if should:
        try:
            import intervene_assign as ia
            from _common import queue_bucket_rows, resolve_queue_path

            report = dict(payload)
            if not ia.rows_from_report(report):
                chair, digest = resolve_homes(args)
                qpath = resolve_queue_path(chair, digest)
                if qpath.is_file():
                    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
                    report["unaccepted"] = queue_bucket_rows(queue, "unaccepted")
            outbox = Path(getattr(args, "ear_outbox", "") or ia.default_ear_outbox())
            dry_i = bool(getattr(args, "intervene_dry_run", False))
            chair, digest = resolve_homes(args)
            offerable_fn = ia._offerable_fn_from_homes(chair, digest)
            inter = ia.intervene_from_report(
                report,
                outbox=outbox,
                dry_run=dry_i,
                force_needs_human=bool(getattr(args, "force_needs_human", False)),
                pace_s=float(getattr(args, "pace_s", 3.0) or 3.0),
                truncate=bool(getattr(args, "truncate_outbox", False)),
                offerable_fn=offerable_fn,
            )
            payload["intervene"] = inter
            notes = list(payload.get("notes") or [])
            if inter.get("written_count", 0) > 0:
                notes.append(
                    f"FR #9461 intervene wrote {inter['written_count']} !assign line(s) to {outbox}"
                )
            elif dry_i and inter.get("planned"):
                notes.append(
                    f"FR #9461 intervene dry-run planned {len(inter['planned'])} !assign line(s)"
                )
            else:
                notes.append("FR #9461 intervene ran but planned 0 assigns")
            payload["notes"] = notes
        except Exception as e:
            notes = list(payload.get("notes") or [])
            notes.append(f"FR #9461 intervene error: {e}")
            payload["notes"] = notes
            findings = list(payload.get("findings") or [])
            findings.append(f"intervene failed: {e}")
            payload["findings"] = findings
    else:
        payload["intervene"] = None
    return emit(payload, code)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
