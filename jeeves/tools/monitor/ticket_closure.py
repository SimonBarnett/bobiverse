#!/usr/bin/env python3
"""FR #6063: report newly closed issues/PRs on watched/focused repos.

Phase-1 events: issue closed, PR merged, PR closed (unmerged).
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
    resolve_focus_path,
    resolve_homes,
    run_check,
)

STATE_NAME = "ticket_closure_state.json"


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
    kind = str(row.get("kind") or "").strip().lower()
    repo = str(row.get("repo") or "").strip()
    num = str(row.get("number") or "").strip()
    ev = str(row.get("event") or "").strip().lower()
    return f"{kind}:{repo}#{num}:{ev}"


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


def check(args):
    chair, digest = resolve_homes(args)
    focus_path = resolve_focus_path(chair, digest)
    repos = _focus_repos(focus_path)
    fx = (os.environ.get("JEEVES_TICKET_CLOSURE_FIXTURE") or "").strip()
    fixture = Path(fx) if fx else None
    events = _load_events(fixture, repos)
    state_path = chair / STATE_NAME
    state = _load_json(state_path)
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
