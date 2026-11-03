#!/usr/bin/env python3
"""FR #6063 / #6064 / #6069: newly closed tickets on watched/focused repos.

Phase-1 events: issue closed, PR merged, PR closed (unmerged).
Phase-2: optional waiting_on registry narrows reports.
Reads a fixture when JEEVES_TICKET_CLOSURE_FIXTURE is set (tests / offline).
Never writes queue.json and never assigns work.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    ops_home,
    resolve_focus_path,
    resolve_homes,
    run_check,
)

STATE_NAME = "monitor-ticket-closure.json"
_LEGACY_STATE_NAME = "ticket_closure_state.json"
WAITING_NAME = "ticket-closure-waiting.json"


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _focus_repos(focus_path: Path) -> set[str]:
    data = _load_json(focus_path)
    if not isinstance(data, dict):
        return set()
    repos = data.get("repos")
    if isinstance(repos, dict):
        return {str(k).strip() for k in repos if str(k).strip()}
    if isinstance(repos, list):
        return {str(r).strip() for r in repos if str(r).strip()}
    return set()


def _event_key(row: dict[str, Any]) -> str:
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("number") or "").strip()
    ev = str(row.get("event") or "").strip().lower()
    ident = str(row.get("delivery_id") or row.get("closed_at") or "").strip()
    return f"{repo}#{num}:{ev}:{ident}"


def _normalize(row: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(row.get("kind") or "").strip().lower()
    ev = str(row.get("event") or "").strip().lower()
    repo = str(row.get("repo") or "").strip()
    try:
        number = int(row.get("number"))
    except (TypeError, ValueError):
        return None
    if kind not in {"issue", "pr"} or not repo or number <= 0:
        return None
    if kind == "issue" and ev != "closed":
        return None
    if kind == "pr" and ev not in {"merged", "closed"}:
        return None
    if kind == "pr" and ev == "closed" and row.get("merged") is True:
        ev = "merged"
    out = {
        "kind": kind,
        "event": ev,
        "repo": repo,
        "number": number,
    }
    closed_at = str(row.get("closed_at") or "").strip()
    delivery = str(row.get("delivery_id") or row.get("deliveryId") or "").strip()
    if closed_at:
        out["closed_at"] = closed_at
    if delivery:
        out["delivery_id"] = delivery
    if kind == "pr":
        out["merged"] = ev == "merged"
    return out


def _load_events(fixture: Path | None, repos: set[str]) -> list[dict[str, Any]]:
    if fixture is None or not fixture.is_file():
        return []
    data = _load_json(fixture)
    rows = []
    if isinstance(data, dict):
        raw = data.get("closed")
        if isinstance(raw, list):
            rows = [r for r in raw if isinstance(r, dict)]
    elif isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    out = []
    for row in rows:
        norm = _normalize(row)
        if not norm:
            continue
        if repos and norm["repo"] not in repos and norm["repo"].rsplit("/", 1)[-1] not in {
            r.rsplit("/", 1)[-1] for r in repos
        }:
            continue
        out.append(norm)
    return out


def _canon_ticket(text: str) -> str:
    return str(text or "").strip().lower().lstrip("#")


def _event_ticket_id(row: dict[str, Any]) -> str:
    return _canon_ticket(f"{row.get('repo')}#{row.get('number')}")


def _load_waiting(chair: Path, digest: Path) -> set[str]:
    """Phase-2 registry. Empty / missing → Phase-1 (all focused closes)."""
    env = (os.environ.get("JEEVES_TICKET_CLOSURE_WAITING") or "").strip()
    paths = []
    if env:
        paths.append(Path(env))
    ops = ops_home(chair, digest)
    paths.extend(
        [
            ops / WAITING_NAME,
            digest / WAITING_NAME,
            chair / WAITING_NAME,
        ]
    )
    for path in paths:
        data = _load_json(path)
        raw = None
        if isinstance(data, dict):
            raw = data.get("waiting_on")
            if raw is None:
                raw = data.get("waitingOn")
        elif isinstance(data, list):
            raw = data
        if not isinstance(raw, list) or not raw:
            continue
        ids = {_canon_ticket(x) for x in raw if str(x).strip()}
        if ids:
            return ids
    return set()


def check(args):
    chair, digest = resolve_homes(args)
    focus_path = resolve_focus_path(chair, digest)
    repos = _focus_repos(focus_path)
    fx = (os.environ.get("JEEVES_TICKET_CLOSURE_FIXTURE") or "").strip()
    fixture = Path(fx) if fx else None
    events = _load_events(fixture, repos)
    waiting = _load_waiting(chair, digest)
    if waiting:
        events = [ev for ev in events if _event_ticket_id(ev) in waiting]
    ops = ops_home(chair, digest)
    state_path = ops / STATE_NAME
    state = _load_json(state_path)
    if state is None:
        state = _load_json(ops / _LEGACY_STATE_NAME) or _load_json(
            chair / _LEGACY_STATE_NAME
        )
    seen = {}
    if isinstance(state, dict) and isinstance(state.get("seen"), dict):
        seen = {str(k): v for k, v in state["seen"].items()}
    closed = []
    for ev in events:
        key = _event_key(ev)
        if key not in seen:
            closed.append(ev)
            seen[key] = ev
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"seen": seen}, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass
    ok = not closed
    findings = []
    remediation = []
    if closed:
        findings.append(f"{len(closed)} newly closed ticket(s) on watched/focused repos")
        remediation.append("report via intake only; do not enqueue or assign")
    return (
        {
            "ok": ok,
            "closed": closed,
            "closed_count": len(closed),
            "repos": sorted(repos),
            "waiting_on": sorted(waiting),
            "findings": findings,
            "remediation": remediation,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "ticket_closure",
        "FR #6063: newly closed issues/PRs on focused repos (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
