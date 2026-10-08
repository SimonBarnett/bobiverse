#!/usr/bin/env python3
"""Monitor check: focus file present / stale (NOT the retired BobAutoFocus ops spammer).

FR #3190 retired ``C:\\ai\\ops\\auto-focus.py`` / scheduled task ``BobAutoFocus``, which
appended per-item ``!focus`` lines every 2 minutes. This module only *reads* focus.json
for Jeeves MONITORING health — it never writes focus or PRIVMSG.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_focus_path, resolve_homes, run_check


def _repo_count(repos) -> int:
    """FR #1043: focus.repos may be a list or a dict of repo -> meta."""
    if isinstance(repos, list):
        return len(repos)
    if isinstance(repos, dict):
        return len(repos)
    return 0


def _repos_empty(repos) -> bool:
    return _repo_count(repos) == 0


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    focus_path = resolve_focus_path(chair, digest)
    if not focus_path.is_file():
        # Missing focus is informational: chair may use empty focus (all repos)
        return (
            {
                "ok": True,
                "configured": False,
                "findings": [],
                "note": "focus.json absent (chair may offer all repos)",
                "path": str(focus_path),
                "ops_home": str(focus_path.parent),
            },
            EXIT_OK,
        )
    try:
        data = json.loads(focus_path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        findings.append(f"focus.json unreadable: {e}")
        return ({"ok": False, "findings": findings, "path": str(focus_path)}, EXIT_FINDING)
    age = time.time() - focus_path.stat().st_mtime
    strict = False
    repos = []
    if isinstance(data, dict):
        strict = bool(data.get("strict"))
        repos = data.get("repos") or data.get("focus") or data.get("items") or []
    elif isinstance(data, list):
        repos = data
    if strict and _repos_empty(repos):
        findings.append("focus strict with empty repo list — assigns will starve")
    ok = not findings
    return (
        {
            "ok": ok,
            "configured": True,
            "strict": strict,
            "repo_count": _repo_count(repos),
            "age_sec": int(age),
            "path": str(focus_path),
            "ops_home": str(focus_path.parent),
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "auto_focus",
        "Auto-focus / focus.json sanity (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
