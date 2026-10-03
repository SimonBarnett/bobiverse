#!/usr/bin/env python3
"""Focus-presence check (FR #1019): bobiverse must stay in focus under strict + queue work."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, queue_bucket_rows, resolve_homes, run_check

REQUIRED_REPO = "simonbarnett/bobiverse"
# Soft expectation for healthy multi-repo focus (reported, not hard-fail alone).
EXPECTED_FALLBACKS = (
    "simonbarnett/xai-cookbook",
    "simonbarnett/agentic_fomprep",
)


def _normalize_repos(raw) -> set[str]:
    out: set[str] = set()
    if isinstance(raw, dict):
        for k in raw.keys():
            s = str(k).strip().lower()
            if s:
                out.add(s)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                s = item.strip().lower()
            elif isinstance(item, dict):
                s = str(item.get("repo") or item.get("name") or "").strip().lower()
            else:
                s = ""
            if s:
                out.add(s)
    return out


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(args):
    chair, _digest = resolve_homes(args)
    findings = []
    remediation = []
    focus_path = chair / "focus.json"
    queue_path = chair / "queue.json"
    focus = _load_json(focus_path) if focus_path.is_file() else None
    queue = _load_json(queue_path) if queue_path.is_file() else {}
    unaccepted = queue_bucket_rows(queue or {}, "unaccepted")
    strict = False
    repos: set[str] = set()
    if isinstance(focus, dict):
        strict = bool(focus.get("strict"))
        repos = _normalize_repos(focus.get("repos") or focus.get("focus") or [])
        # item-level focus repos also count
        items = focus.get("items")
        if isinstance(items, dict):
            for meta in items.values():
                if isinstance(meta, dict) and meta.get("repo"):
                    repos.add(str(meta["repo"]).strip().lower())
    elif isinstance(focus, list):
        repos = _normalize_repos(focus)

    has_bobiverse = any(
        r == REQUIRED_REPO or r.endswith("/bobiverse") or r == "bobiverse" for r in repos
    )
    missing_fallbacks = [r for r in EXPECTED_FALLBACKS if r not in repos]

    if not focus_path.is_file():
        if unaccepted:
            findings.append(
                "focus.json missing while unaccepted rows exist (focus-lost risk)"
            )
            remediation.append("restore focus.json with SimonBarnett/bobiverse (+ fallbacks)")
    elif strict and unaccepted:
        if not repos:
            findings.append(
                "focus.strict with empty repos while unaccepted work exists (hides whole queue)"
            )
            remediation.append("!focus SimonBarnett/bobiverse (and expected fallbacks)")
        elif not has_bobiverse:
            findings.append(
                "focus.strict missing SimonBarnett/bobiverse while unaccepted rows exist"
            )
            remediation.append("add SimonBarnett/bobiverse to focus.repos")

    ok = not findings
    return (
        {
            "ok": ok,
            "strict": strict,
            "has_bobiverse": has_bobiverse,
            "repo_count": len(repos),
            "repos": sorted(repos),
            "missing_fallbacks": missing_fallbacks,
            "unaccepted_count": len(unaccepted),
            "path": str(focus_path),
            "findings": findings,
            "remediation": remediation,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "focus_present",
        "Focus presence: bobiverse under strict + unaccepted (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
