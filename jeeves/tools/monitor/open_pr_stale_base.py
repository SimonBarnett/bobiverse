#!/usr/bin/env python3
"""FR #8333: open PRs whose base is not the default branch (main/master).

Cheap hygiene: flag pulls that cannot land on main until retargeted
(``gh pr edit --base main``) or recreated. Class of bobiverse#8320
(fix(mrb-8316) stuck on merged ``fr-8310-land`` while #8331 stayed open).

Offline: set ``JEEVES_OPEN_PR_STALE_BASE_FIXTURE`` to a JSON list of pull
payloads (GitHub ``/pulls`` shape with ``base.ref``). Live chair may inject
the same list via that env after ``gh pr list --json``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from _common import EXIT_FINDING, EXIT_OK, run_check


def _ensure_common() -> None:
    here = Path(__file__).resolve().parent
    for cand in (
        here.parents[2] / "common" / "scripts",
        here.parents[1] / "scripts",
        here.parents[1] / "common" / "scripts",
    ):
        if (cand / "gitclaim.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            return


def _load_fixture(path: str) -> list[Any]:
    raw = Path(path).read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, dict):
        pulls = data.get("pulls") or data.get("items") or data.get("prs")
        if isinstance(pulls, list):
            return pulls
        return []
    return data if isinstance(data, list) else []


def check(args):
    _ensure_common()
    import gitclaim as gc

    fixture = (os.environ.get("JEEVES_OPEN_PR_STALE_BASE_FIXTURE") or "").strip()
    if not fixture:
        return (
            {
                "ok": True,
                "skipped": "no_fixture",
                "findings": [],
                "stale": [],
                "hint": (
                    "set JEEVES_OPEN_PR_STALE_BASE_FIXTURE to a JSON pull list, "
                    "or rely on github-resync FR #8333 skip/warn lines"
                ),
            },
            EXIT_OK,
        )

    try:
        pulls = _load_fixture(fixture)
    except (OSError, json.JSONDecodeError) as exc:
        return (
            {
                "ok": False,
                "findings": [f"fixture read failed: {type(exc).__name__}"],
                "stale": [],
                "path_fixture": fixture,
            },
            EXIT_FINDING,
        )

    stale = gc.list_open_prs_explicit_non_default_base(pulls)
    findings = [
        (
            f"open PR #{row.get('number')} base={row.get('base')} "
            f"cannot land on default branch until retarget/recreate "
            f"({row.get('title') or ''})"
        )
        for row in stale
    ]
    remediation = [
        "gh pr edit <n> --base main  (when the tip is mergeable onto main)",
        "or close and recreate the tip on a fresh fr-N from origin/main",
        "github-resync skips orphan fix(mrb-N) with explicit non-default base (FR #8333)",
    ]
    ok = not findings
    return (
        {
            "ok": ok,
            "findings": findings,
            "remediation": remediation if findings else [],
            "stale": stale,
            "path_fixture": fixture,
            "pull_count": len(pulls) if isinstance(pulls, list) else 0,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "open_pr_stale_base",
        "open PRs with non-default base (FR #8333)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
