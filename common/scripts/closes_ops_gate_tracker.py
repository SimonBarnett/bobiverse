#!/usr/bin/env python3
"""FR #9400: refuse Closes on ops/gate tracker issues while gate markers remain.

Umbrella / ops rebuild-install trackers (Depends-on, GateIssues, unchecked
acceptance) must use Refs / Toward until gates are CLOSED and acceptance is
done. Tool-only PRs must not Closes those trackers (live: #9376 closed by #9387).

Pure helpers + CLI for stamp JSON or --pr-body / --issue-body files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_CLOSES = re.compile(
    r"(?i)\bCloses\s+(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s*)?#(\d+)\b"
)
_REFS_ONLY = re.compile(
    r"(?i)\b(?:Refs|Toward)\s+(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s*)?#(\d+)\b"
)
_DEPENDS = re.compile(r"(?im)^\s*Depends-on:\s*(.+?)\s*$")
_GATE_HEAD = re.compile(r"(?im)^\s*(?:##\s*)?GateIssues\b")
_UNCHECKED = re.compile(r"(?m)^\s*-\s*\[\s\]\s+\S+")
_OPS_PHRASE = re.compile(
    r"(?is)(?:ops\s+install\s+NOT\s+done|walrus\s+rebuild/install\s+tracker|"
    r"do\s+not\s+`?Closes`?.*(?:GateIssues|Depends-on)|"
    r"tool-only\s+PRs?\s+link\s+with\s+`?Refs)"
)


def closes_issue_numbers(pr_body: str) -> set[int]:
    out: set[int] = set()
    for m in _CLOSES.finditer(pr_body or ""):
        out.add(int(m.group(2)))
    return out


def issue_has_open_gate_markers(body: str) -> bool:
    """True when issue body still advertises open gate / acceptance work."""
    text = body or ""
    if _GATE_HEAD.search(text):
        return True
    if _OPS_PHRASE.search(text):
        return True
    m = _DEPENDS.search(text)
    if m:
        val = m.group(1).strip().lower()
        if val and val not in ("(none)", "none", "-", "n/a", "n\\a"):
            return True
    if _UNCHECKED.search(text) and re.search(
        r"(?i)acceptance|gate|install|depends-on", text
    ):
        return True
    return False


def check_pr_against_issues(
    pr_body: str, issues: dict[int, str]
) -> list[str]:
    """Return error strings when Closes targets still look like open gate trackers."""
    errs: list[str] = []
    targets = closes_issue_numbers(pr_body)
    if not targets:
        return errs
    for num in sorted(targets):
        body = issues.get(num)
        if body is None:
            continue
        if issue_has_open_gate_markers(body):
            errs.append(
                f"Closes #{num} while issue body still has open Depends-on / "
                f"GateIssues / unchecked acceptance (FR #9400) — use Refs/Toward"
            )
    return errs


def check_stamp(data: dict[str, Any]) -> list[str]:
    if not isinstance(data, dict):
        return ["stamp root must be an object"]
    pr_body = str(data.get("pr_body") or data.get("body") or "")
    issues_raw = data.get("issues") or {}
    issues: dict[int, str] = {}
    if isinstance(issues_raw, dict):
        for k, v in issues_raw.items():
            try:
                issues[int(str(k).lstrip("#"))] = (
                    str(v.get("body") if isinstance(v, dict) else v) or ""
                )
            except ValueError:
                continue
    elif isinstance(issues_raw, list):
        for item in issues_raw:
            if not isinstance(item, dict):
                continue
            try:
                n = int(str(item.get("number") or item.get("id") or "").lstrip("#"))
            except ValueError:
                continue
            issues[n] = str(item.get("body") or "")
    return check_pr_against_issues(pr_body, issues)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="FR #9400 Closes vs open gate tracker check")
    p.add_argument("stamp", nargs="?", help="JSON stamp path")
    p.add_argument("--pr-body", default="", help="PR body file")
    p.add_argument("--issue-body", action="append", default=[], help="issueNum=path")
    args = p.parse_args(argv)
    if args.stamp:
        data = json.loads(Path(args.stamp).read_text(encoding="utf-8"))
        errs = check_stamp(data)
    else:
        pr_body = (
            Path(args.pr_body).read_text(encoding="utf-8") if args.pr_body else ""
        )
        issues: dict[int, str] = {}
        for spec in args.issue_body:
            if "=" not in spec:
                print(f"bad --issue-body {spec!r} (want N=path)", file=sys.stderr)
                return 2
            num_s, path = spec.split("=", 1)
            issues[int(num_s.lstrip("#"))] = Path(path).read_text(encoding="utf-8")
        errs = check_pr_against_issues(pr_body, issues)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
