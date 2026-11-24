#!/usr/bin/env python3
"""MRB same-machine starve / soft free= drift (FR #9478).

EXIT 0: no starve — idle same-machine siblings are offerable under soft free=
policy, or a free cross-machine reviewer exists for every blocked case.
EXIT 1: idle same-machine non-author seats are blocked from offerable MRBs
while no free cross-machine reviewer can take them (hard machine-id starve or
a call path that omitted free=).
EXIT 2: error.

Never Start-BobWorker / WinRM install / Ergo. Report-only; prefer cross-machine
!assign via intervene_assign / idle push.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _common import (
    EXIT_ERROR,
    EXIT_FINDING,
    EXIT_OK,
    ops_home,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

FINGERPRINT_ID = "mrb-same-machine-starve"
REMEDIATION = (
    "FR #9478: soft free-other-machine MRB block + prefer cross-machine "
    "reviewers. Until tip jeeves.exe is installed, !assign cross-machine "
    "idle seats (e.g. redqueen) to flamingo-authored MRBs. Do not WinRM "
    "rebuild from this check (Depends-on #9475/#9476)."
)


def fingerprint_for(repo: str, ident: str, machine: str) -> str:
    r = str(repo or "").strip() or "?"
    i = str(ident or "").strip().lstrip("#") or "?"
    m = str(machine or "").strip().lower() or "?"
    return f"stall:{FINGERPRINT_ID}:{r}#{i}:{m}"


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_gitclaim():
    from _common import ensure_script_dir_on_path

    ensure_script_dir_on_path("gitclaim.py")
    import gitclaim  # noqa: WPS433

    return gitclaim


def _seat_mid(gc, nick: str) -> str:
    n = (gc.canonical_worker_nick(nick) or nick or "").strip()
    if not n:
        return ""
    try:
        import bobreport

        p = bobreport.parse_seat_nick(n)
        if p:
            return bobreport.fold_machine_id(p[0])
    except Exception:
        pass
    if "-" in n:
        return n.rsplit("-", 1)[0].lower()
    return ""


def collect_starve_cases(
    home: Path,
    *,
    unaccepted: list[dict] | None = None,
    idle_nicks: list[str] | None = None,
    live: set[str] | None = None,
    free: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Idle same-machine siblings blocked with no free cross-machine reviewer."""
    gc = _ensure_gitclaim()
    try:
        doc = gc.load_queue(home) if hasattr(gc, "load_queue") else None
    except Exception:
        doc = None
    if not isinstance(doc, dict):
        doc = {"v": 1, "unaccepted": list(unaccepted or []), "accepted": [], "done": []}
    rows = list(unaccepted) if unaccepted is not None else list(doc.get("unaccepted") or [])
    rows = [r for r in rows if isinstance(r, dict) and str(r.get("task") or "").upper() == "MRB"]
    if not rows:
        return []

    live_set = set(live) if live is not None else set(gc.live_seat_nicks(home) or [])
    free_set = (
        set(free)
        if free is not None
        else set(gc.free_seat_nicks(home, live_set) or [])
    )
    if idle_nicks is None:
        try:
            import idle_seats as _idle

            dig = _load_json(Path(home) / "digest.json") or {}
            machines = dig.get("machines") if isinstance(dig, dict) else {}
            idle_nicks = [
                str(s.get("nick") or "")
                for s in _idle.collect_idle_shop_seats(machines)
                if str(s.get("nick") or "").strip()
            ]
        except Exception:
            idle_nicks = sorted(free_set)

    idle_nicks = [n for n in (idle_nicks or []) if str(n).strip()]
    if not idle_nicks:
        return []

    try:
        ledger = gc.ledger_load(home)
    except Exception:
        ledger = {}

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        cand = gc.enrich_review_author_fields(doc, row)
        if not gc.mrb_row_offerable(cand, pr_exists=None):
            continue
        repo = str(cand.get("repo") or "")
        ident = str(cand.get("id") or "")
        # Free cross-machine reviewers that tip soft policy allows.
        free_cross: list[str] = []
        for n in free_set:
            n_c = (gc.canonical_worker_nick(n) or n or "").strip()
            if not n_c:
                continue
            if gc.review_blocked_for_author(
                cand, n_c, live_set | {n_c}, ledger=ledger, free=free_set
            ):
                continue
            # Cross-machine relative to at least one author mid.
            author_mids = {
                _seat_mid(gc, a) for a in gc.row_author_seats(cand) if _seat_mid(gc, a)
            }
            mid = _seat_mid(gc, n_c)
            if mid and author_mids and mid not in author_mids:
                free_cross.append(n_c)
        if free_cross:
            # Prefer path exists — not a same-machine starve.
            continue
        for nick in idle_nicks:
            me = (gc.canonical_worker_nick(nick) or nick or "").strip()
            if not me:
                continue
            authors = {a.lower() for a in gc.row_author_seats(cand)}
            if me.lower() in authors:
                continue  # exact author — expected block
            mid = _seat_mid(gc, me)
            author_mids = {
                _seat_mid(gc, a) for a in gc.row_author_seats(cand) if _seat_mid(gc, a)
            }
            if not mid or mid not in author_mids:
                continue  # not same-machine sibling
            blocked_soft = gc.review_blocked_for_author(
                cand, me, live_set | {me}, ledger=ledger, free=free_set
            )
            if not blocked_soft:
                continue  # soft tip allows — no starve
            # Soft still blocks with no free cross → pinned / giveup / ledger.
            # Also detect hard-vs-soft drift (free=None would block more).
            blocked_hard = gc.review_blocked_for_author(
                cand, me, live_set | {me}, ledger=ledger, free=None
            )
            fp = fingerprint_for(repo, ident, mid)
            if fp in seen:
                continue
            seen.add(fp)
            out.append(
                {
                    "repo": repo,
                    "id": ident,
                    "machine": mid,
                    "idle_nick": me,
                    "blocked_soft": bool(blocked_soft),
                    "blocked_hard": bool(blocked_hard),
                    "free_cross": [],
                    "fingerprint": fp,
                    "rule": FINGERPRINT_ID,
                }
            )
    return out


def check(args: Any) -> tuple[dict[str, Any], int]:
    try:
        chair, digest = resolve_homes(args)
    except Exception as exc:
        return (
            {
                "ok": False,
                "fr": 9478,
                "findings": [f"resolve_homes failed: {type(exc).__name__}"],
            },
            EXIT_ERROR,
        )
    home = ops_home(chair, digest)
    qpath = resolve_queue_path(chair, digest)
    findings: list[str] = []
    notes: list[str] = []
    cases: list[dict[str, Any]] = []
    try:
        cases = collect_starve_cases(home)
    except Exception as exc:
        return (
            {
                "ok": False,
                "fr": 9478,
                "findings": [f"collect failed: {type(exc).__name__}: {exc}"],
                "queue_path": str(qpath),
                "home": str(home),
            },
            EXIT_ERROR,
        )
    for c in cases:
        findings.append(
            f"mrb_same_machine_starve {c.get('repo')}{c.get('id')} "
            f"machine={c.get('machine')} idle={c.get('idle_nick')} "
            f"fingerprint={c.get('fingerprint')}"
        )
    if not cases:
        notes.append("no same-machine MRB starve under soft free= policy")
    ok = not findings
    payload: dict[str, Any] = {
        "ok": ok,
        "fr": 9478,
        "check": "mrb_same_machine_starve",
        "findings": findings,
        "cases": cases,
        "fingerprints": [str(c.get("fingerprint") or "") for c in cases],
        "remediation": REMEDIATION if cases else "",
        "notes": notes,
        "queue_path": str(qpath),
        "home": str(home),
    }
    return payload, EXIT_OK if ok else EXIT_FINDING


def main(argv=None) -> int:
    return run_check(
        "mrb_same_machine_starve",
        "MRB same-machine starve / soft free= drift (FR #9478; exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
