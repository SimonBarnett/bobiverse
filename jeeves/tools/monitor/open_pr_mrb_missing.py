#!/usr/bin/env python3
"""FR #8377 / #9635: open PRs missing from the MRB (or FIX) queue.

An open non-draft non-receipt product PR with no unaccepted/accepted MRB (or FIX)
row is stranded: seats can never be offered the hostile review for a green,
mergeable PR (class of bobiverse#8353, whose open PR never reached the queue).

FR #9635: default heal enqueues missing expected MRB rows into the chair queue
(same classification as ``!resync`` / ``heal_open_prs_missing_mrb``), including
``lesson(...)`` / harvest-lesson tips. Report-only: ``--no-heal``.

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
    build_parser,
    emit,
    resolve_homes,
    resolve_queue_path,
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

    pulls_l = pulls if isinstance(pulls, list) else []
    expected = [
        p for p in pulls_l
        if isinstance(p, dict) and gc.open_pr_expects_mrb_or_fix_row(p)
    ]
    missing = gc.list_open_prs_missing_mrb(pulls_l, queue, repo=repo)

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

    heal_requested = bool(getattr(args, "heal", True))
    heal_result = None
    notes: list[str] = []
    # FR #9635: enqueue missing expected MRBs into the chair queue (default ON).
    # Needs a writable queue home; skip when queue.json was missing (finding stays).
    if heal_requested and missing and queue is not None:
        heal_home = Path(queue_path).parent
        heal_result = gc.heal_open_prs_missing_mrb(
            heal_home,
            pulls_l,
            repo=repo,
            dry_run=bool(getattr(args, "heal_dry_run", False)),
        )
        notes.append(
            "FR #9635 heal "
            f"added={heal_result.get('added')} "
            f"dup={heal_result.get('duplicate')} "
            f"missing_before={heal_result.get('missing_before')} "
            f"missing_after={heal_result.get('missing_after')} "
            f"dry_run={heal_result.get('dry_run')}"
        )
        if heal_result.get("ok") and int(heal_result.get("missing_after") or 0) == 0:
            # Correlated enqueue within this check cycle — clear stranded findings.
            findings = []
            missing = []
            remediation = []

    ok = not findings
    return (
        {
            "ok": ok,
            "findings": findings,
            "remediation": remediation if findings else [],
            "notes": notes,
            "missing": missing,
            "expected_count": len(expected),
            "missing_count": len(missing),
            "repo": repo,
            "path_fixture": fixture,
            "path_queue": str(queue_path),
            "heal_requested": heal_requested,
            "heal": heal_result,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    p = build_parser(
        "open_pr_mrb_missing",
        "open PRs missing from the MRB/FIX queue (FR #8377 / #9635)",
    )
    # FR #9635: default heal ON (report-only requires --no-heal).
    p.add_argument(
        "--heal",
        dest="heal",
        action="store_true",
        default=True,
        help="enqueue missing expected MRB rows into the chair queue (default)",
    )
    p.add_argument(
        "--no-heal",
        dest="heal",
        action="store_false",
        help="report-only: do not enqueue missing MRB rows",
    )
    p.add_argument(
        "--heal-dry-run",
        action="store_true",
        help="plan heal enqueue without writing queue.json",
    )
    args = p.parse_args(argv)
    if args.dry_run:
        return emit(
            {
                "check": "open_pr_mrb_missing",
                "ok": True,
                "dry_run": True,
                "findings": [],
            },
            EXIT_OK,
        )
    try:
        payload, code = check(args)
        payload.setdefault("check", "open_pr_mrb_missing")
        payload.setdefault("dry_run", False)
        return emit(payload, code)
    except Exception as e:
        return emit(
            {
                "check": "open_pr_mrb_missing",
                "ok": False,
                "dry_run": False,
                "error": f"{type(e).__name__}: {e}",
                "findings": [str(e)],
            },
            2,
        )


if __name__ == "__main__":
    raise SystemExit(main())
