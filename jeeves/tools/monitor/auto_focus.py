#!/usr/bin/env python3
"""Auto-focus check (ported intent from ops/auto-focus.py): focus file present / stale."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_homes, run_check


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    focus_path = chair / "focus.json"
    if not focus_path.is_file():
        # Missing focus is informational: chair may use empty focus (all repos)
        return (
            {
                "ok": True,
                "configured": False,
                "findings": [],
                "note": "focus.json absent (chair may offer all repos)",
                "path": str(focus_path),
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
    if strict and not repos:
        findings.append("focus strict with empty repo list — assigns will starve")
    ok = not findings
    return (
        {
            "ok": ok,
            "configured": True,
            "strict": strict,
            "repo_count": len(repos) if isinstance(repos, list) else 0,
            "age_sec": int(age),
            "path": str(focus_path),
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
