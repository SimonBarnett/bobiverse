#!/usr/bin/env python3
"""FR #8377: open PRs missing from the MRB (or FIX) queue.

An open non-draft non-receipt product PR with no unaccepted/accepted MRB (or FIX)
row is stranded: seats can never be offered the hostile review for a green,
mergeable PR (class of bobiverse#8353, whose open PR never reached the queue).

Offline: set ``JEEVES_OPEN_PR_MRB_MISSING_FIXTURE`` to a JSON pull list (GitHub
``/pulls`` shape). Each pull may carry ``base.repo.full_name``, or the whole
fixture may be ``{"repo": "owner/name", "pulls": [...]}``. The chair injects its
focus-repo open pulls the same way after ``gh pr list --json``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    resolve_homes,
    resolve_queue_path,
    run_check,
)


def _ensure_common() -> None:
    from _common import ensure_script_dir_on_path

    # FR #8580 / #8591: no parents[N]; walk upward for gitclaim.py
    ensure_script_dir_on_path("gitclaim.py")



def _load_fixture(path: str) -> tuple[str, list[Any]]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, dict):
        repo = str(data.get("repo") or "")
        pulls = data.get("pulls") or data.get("items") or data.get("prs")
        if isinstance(pulls, list):
            return repo, pulls
        return repo, []
    return "", (data if isinstance(data, list) else [])


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def check(args):
    _ensure_common()
    import gitclaim as gc

    fixture = (os.environ.get("JEEVES_OPEN_PR_MRB_MISSING_FIXTURE") or "").strip()
    if not fixture:
        return (
            {
                "ok": True,
                "skipped": "no_fixture",
                "findings": [],
                "missing": [],
                "hint": (
                    "set JEEVES_OPEN_PR_MRB_MISSING_FIXTURE to a JSON pull list "
                    "(focus-repo open pulls) to check queue coverage"
                ),
            },
            EXIT_OK,
        )

    try:
        repo, pulls = _load_fixture(fixture)
    except (OSError, json.JSONDecodeError) as exc:
        return (
            {
                "ok": False,
                "findings": [f"fixture read failed: {type(exc).__name__}"],
                "missing": [],
                "path_fixture": fixture,
            },
            EXIT_FINDING,
        )

    chair, digest = resolve_homes(args)
    queue_path = resolve_queue_path(chair, digest)
    queue = _load_json(queue_path)
    if not isinstance(queue, dict):
        queue = None

    expected = [
        p for p in (pulls if isinstance(pulls, list) else [])
        if isinstance(p, dict) and gc.open_pr_expects_mrb_or_fix_row(p)
    ]
    missing = gc.list_open_prs_missing_mrb(
        pulls if isinstance(pulls, list) else [], queue, repo=repo
    )

    findings: list[str] = []
    if queue is None:
        findings.append(f"queue.json missing at {queue_path}")
    for row in missing:
        repo_s = row.get("repo") or repo or "?"
        num = row.get("number")
        findings.append(
            f"open PR {repo_s}#{num} has no unaccepted/accepted MRB or FIX row "
            f"({row.get('title') or ''})"
        )

    remediation = [
        "run !resync (or wait for the hourly/gap github_resync) to re-enqueue the MRB",
        "clear a stale merge-on-green PASS / done[] ci-wait hold for the PR "
        "(false ci-wait parks the row; FR #8377)",
        "confirm the pull list fetch is not stuck on a 304/ETag (FR #4959)",
    ]
    ok = not findings
    return (
        {
            "ok": ok,
            "findings": findings,
            "remediation": remediation if findings else [],
            "missing": missing,
            "expected_count": len(expected),
            "missing_count": len(missing),
            "repo": repo,
            "path_fixture": fixture,
            "path_queue": str(queue_path),
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "open_pr_mrb_missing",
        "open PRs missing from the MRB/FIX queue (FR #8377)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
