#!/usr/bin/env python3
"""Detect github_resync repos=0 starve when focus has repos (FR #3146).

Finding when focus.repos is non-empty, unaccepted is empty, and discover_repos
still yields no repos (or yields focus repos while the queue stayed empty after
a no-repos early return — ops tip: write resync-repos.txt / !resync).

After the product fix, discover_repos unions focus; a lasting finding is:
focus non-empty + unaccepted==0 + discover returns focus repos → queue never
filled (need !resync / Sync). We treat discover empty with non-empty focus as
the hard product bug; discover non-empty + unaccepted==0 as ops lag finding.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    ops_home,
    resolve_focus_path,
    resolve_homes,
    resolve_queue_path,
    run_check,
)


def _ensure_common() -> None:
    here = Path(__file__).resolve().parent
    for cand in (
        here.parents[2] / "common" / "scripts",
        here.parents[1] / "scripts",
        here.parents[1] / "common" / "scripts",
    ):
        if (cand / "chair_health.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            return


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _focus_repo_count(path: Path) -> int:
    data = _load_json(path)
    if not isinstance(data, dict):
        return 0
    repos = data.get("repos")
    if isinstance(repos, dict):
        return len(repos)
    if isinstance(repos, list):
        return len(repos)
    return 0


def _unaccepted_count(queue_path: Path) -> int:
    data = _load_json(queue_path)
    if not isinstance(data, dict):
        return 0
    rows = data.get("unaccepted") or []
    return len(rows) if isinstance(rows, list) else 0


def check(args):
    _ensure_common()
    import chair_health as ch

    chair, digest = resolve_homes(args)
    focus_path = resolve_focus_path(chair, digest)
    queue_path = resolve_queue_path(chair, digest)
    home = ops_home(chair, digest)
    findings: list[str] = []
    remediation: list[str] = []

    focus_n = _focus_repo_count(focus_path)
    unacc = _unaccepted_count(queue_path)
    if focus_n == 0:
        return (
            {
                "ok": True,
                "focus_repo_count": 0,
                "unaccepted": unacc,
                "discover_repos": [],
                "findings": [],
                "path_focus": str(focus_path),
                "path_queue": str(queue_path),
                "ops_home": str(home),
            },
            EXIT_OK,
        )

    def getter(url):
        return []

    discovered = ch.discover_repos(home, {"simonbarnett"}, getter, ignored=[])
    # Prefer focus home when focus.json is beside digest but ops_home picked queue elsewhere.
    if not discovered and focus_path.parent != home:
        discovered = ch.discover_repos(focus_path.parent, {"simonbarnett"}, getter, ignored=[])

    if not discovered:
        findings.append(
            "focus.repos non-empty but discover_repos empty (github_resync would log repos=0 / note=no repos)"
        )
        remediation.append(
            "confirm focus keys expand to owner/repo; ensure FR #3146 chair_health.focus_repos is composed on ionos"
        )
        remediation.append(
            "ops: write resync-repos.txt with SimonBarnett/<focused> then !resync"
        )
    elif unacc == 0:
        findings.append(
            f"focus.repos={focus_n} discoverable={discovered} but unaccepted=0 — queue starve / need !resync"
        )
        remediation.append(
            "run !resync on the chair (or wait for hourly/gap github_resync after Sync/compose; FR #3212)"
        )
        remediation.append(
            "ops immediate: digest-home resync-repos.txt with focused full names then !resync"
        )

    ok = not findings
    return (
        {
            "ok": ok,
            "focus_repo_count": focus_n,
            "unaccepted": unacc,
            "discover_repos": discovered,
            "findings": findings,
            "remediation": remediation,
            "path_focus": str(focus_path),
            "path_queue": str(queue_path),
            "ops_home": str(home),
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "github_resync_focus",
        "github_resync repos=0 vs non-empty focus (FR #3146)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
