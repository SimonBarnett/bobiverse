#!/usr/bin/env python3
"""Queue-flow check: gated vs ungated offer queue (FR #1518 / #1508)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    iter_worker_entries,
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


def _ensure_gitclaim():
    here = Path(__file__).resolve().parent
    for cand in (
        here.parents[1] / "scripts",
        here.parents[2] / "common" / "scripts",
        here.parents[1] / "common" / "scripts",
    ):
        if (cand / "gitclaim.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            break
    import gitclaim  # noqa: WPS433

    return gitclaim


def _row_labels(row: dict) -> set[str]:
    labs = row.get("labels") or ()
    if isinstance(labs, str):
        labs = [labs]
    return {str(x).strip().lower() for x in labs if str(x).strip()}


def _gate_bucket(row: dict) -> str:
    """First gate reason for an unaccepted row (FR #1518). Does not change SKIP_FR semantics.

    FR #1523 / #1526: ``needs-mrb1`` is not an offer gate (intake hallucination). Leftover
    labels are reported via notes, not this bucket.
    """
    if row.get("ignored"):
        return "ignored"
    try:
        gc = _ensure_gitclaim()
        skip = gc.row_skip_fr_reason(row)
        if skip:
            # label:skill / harvest_title → skill bucket for operator view
            s = str(skip).lower()
            if "skill" in s or "harvest" in s:
                return "skill"
            return "skip_fr"
        # Global human gate (empty nick): per-seat giveup still counts as needs-human for breakdown.
        if gc.row_needs_human(row, ""):
            return "needs-human"
    except Exception:
        if row.get("needs_human") or str(row.get("needs_human") or "").lower() in (
            "1",
            "true",
            "yes",
        ):
            return "needs-human"
        labs_l = _row_labels(row)
        if "skill" in labs_l or "harvest" in labs_l:
            return "skill"
        if "needs-human" in labs_l:
            return "needs-human"
    rm = str(row.get("require_machine") or "").strip()
    if rm and rm.lower() not in ("*", "any", "none", "-", ""):
        return "require_machine"
    return "ungated"


def _legacy_needs_mrb1_count(unaccepted: list[dict]) -> int:
    return sum(1 for r in unaccepted if "needs-mrb1" in _row_labels(r))


def _count_idle_seats(digest_doc: dict) -> int:
    """FR #1625: shop-form idle seats only (deduped; drop w-mh-* ghosts)."""
    try:
        import idle_seats as _idle

        machines = digest_doc.get("machines") if isinstance(digest_doc, dict) else None
        return len(_idle.collect_idle_shop_seats(machines))
    except Exception:
        n = 0
        machines = digest_doc.get("machines") if isinstance(digest_doc, dict) else None
        for w in iter_worker_entries(machines):
            if str(w.get("state") or "").lower() == "idle":
                nick = str(w.get("nick") or w.get("name") or "")
                if nick.lower().startswith("w-"):
                    continue
                n += 1
        return n


def _pin_zero_seat_note(unaccepted: list[dict], digest_doc: dict) -> str | None:
    """FR #1508: when every live unaccepted row is a require_machine pin."""
    pin_rows = []
    for r in unaccepted:
        rm = str(r.get("require_machine") or "").strip()
        if rm and rm.lower() not in ("*", "any", "none", "-"):
            pin_rows.append(r)
    live_unacc = [r for r in unaccepted if not r.get("ignored")]
    if not pin_rows or len(pin_rows) != len(live_unacc):
        return None
    try:
        import bobreport as _br

        def _fold(mid: str) -> str:
            return _br.fold_machine_id(mid) or str(mid).strip().lower()
    except Exception:
        def _fold(mid: str) -> str:
            return str(mid).strip().lower()

    machines: dict[str, int] = {}
    for mid, ent in ((digest_doc.get("machines") or {}) if isinstance(digest_doc, dict) else {}).items():
        wl = (ent or {}).get("worker_list") if isinstance(ent, dict) else None
        n = len(wl) if isinstance(wl, list) else 0
        key = _fold(str(mid))
        machines[key] = machines.get(key, 0) + n
    missing = sorted(
        {
            _fold(str(r.get("require_machine") or ""))
            for r in pin_rows
            if machines.get(_fold(str(r.get("require_machine") or "")), 0) == 0
        }
        - {""}
    )
    if missing:
        return (
            "offer queue gated: require_machine pins only; no seats on "
            + ",".join(missing)
        )
    return "offer queue gated: require_machine pins only (seats present on pin machines)"


def check(args):
    chair, digest = resolve_homes(args)
    findings: list[str] = []
    notes: list[str] = []
    qpath = resolve_queue_path(chair, digest)
    ops = ops_home(chair, digest)
    queue = _load_json(qpath)
    if queue is None:
        findings.append(f"queue.json missing at {ops} (chair={chair} digest={digest})")
        return (
            {"ok": False, "findings": findings, "notes": notes, "chair_home": str(chair)},
            EXIT_FINDING,
        )
    unaccepted = queue_bucket_rows(queue, "unaccepted")
    dig = _load_json(digest / "digest.json") or {}

    # FR #1518: breakdown of unaccepted by gate (skill harvest usually never enqueued — count stays 0).
    gated_counts = {
        "skill": 0,
        "skip_fr": 0,
        "needs-human": 0,
        "needs-mrb1": 0,
        "require_machine": 0,
        "ignored": 0,
        "ungated": 0,
    }
    for r in unaccepted:
        bucket = _gate_bucket(r)
        gated_counts[bucket] = gated_counts.get(bucket, 0) + 1

    # Seat-aware ungated offerable (same as FR #1116 / idle_seats / #1625).
    offerable_n = 0
    pending_offers = 0
    try:
        import idle_seats as _idle

        pending_offers = sum(
            1 for r in unaccepted if isinstance(r, dict) and _idle.row_offer_pending(r)
        )
        machines = dig.get("machines") if isinstance(dig, dict) else None
        idle_rows = _idle.collect_idle_shop_seats(machines)
        nicks = [str(x.get("nick") or "") for x in idle_rows if x.get("nick")]
        if not nicks:
            # No live shop seats: ungated count is informational only (not starve).
            offerable_n = 0
        else:
            home = qpath.parent
            offerable_n = int(_idle.count_offerable_for_live_seats(home, unaccepted, nicks))
        if pending_offers:
            notes.append(
                f"{pending_offers} unaccepted row(s) offered_to awaiting ACK (excluded from starve; FR #1625)"
            )
    except Exception:
        offerable_n = sum(
            1
            for r in unaccepted
            if not r.get("ignored")
            and not r.get("needs_human")
            and str(r.get("needs_human") or "").lower() not in ("1", "true", "yes")
            and _gate_bucket(r) == "ungated"
            and not str(r.get("offered_to") or "").strip()
        )

    idle_seat_count = _count_idle_seats(dig if isinstance(dig, dict) else {})
    missing_url = [
        r for r in unaccepted if row_task(r) == "MRB" and not row_has_pull_url(r)
    ]

    legacy_mrb1 = _legacy_needs_mrb1_count(unaccepted)
    if legacy_mrb1:
        notes.append(
            f"legacy needs-mrb1 label on {legacy_mrb1} row(s) "
            "(not an offer gate; FR #1523/#1526)"
        )

    # FR #1518: gated-empty is informational (exit 0). True starve = ungated work + idle seats.
    if offerable_n == 0:
        pin_note = _pin_zero_seat_note(unaccepted, dig if isinstance(dig, dict) else {})
        if pin_note:
            notes.append(pin_note)
        else:
            parts = [
                f"{k}={v}"
                for k, v in gated_counts.items()
                if v and k != "ungated"
            ]
            detail = (", ".join(parts)) if parts else "no unaccepted rows"
            notes.append(
                "offer queue gated or empty (no ungated offerable for live seats): "
                + detail
            )
            notes.append(
                "skill/harvest issues are SKIP_FR and never enqueue — open GitHub skill count is outside this queue"
            )
    elif offerable_n > 0 and idle_seat_count > 0:
        findings.append(
            f"true starve: ungated_offerable={offerable_n} idle_seats={idle_seat_count}"
        )

    for r in missing_url[:20]:
        ident = r.get("id") or r.get("number") or "?"
        repo = r.get("repo") or r.get("owner_repo") or "?"
        findings.append(
            f"row missing pull url: {repo}{ident if str(ident).startswith('#') else '#' + str(ident)}"
        )

    ok = not findings
    return (
        {
            "ok": ok,
            "ops_home": str(ops),
            "queue_path": str(qpath),
            "unaccepted_count": len(unaccepted),
            "offerable_count": offerable_n,
            "ungated_offerable_count": offerable_n,
            "idle_seat_count": idle_seat_count,
            "pending_offer_count": pending_offers,
            "gated_counts": gated_counts,
            "missing_pull_url_count": len(missing_url),
            "notes": notes,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "queue_flow",
        "Queue flow: ungated vs gated offer queue / missing pull url (exit 0/1/2; FR #1518)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
