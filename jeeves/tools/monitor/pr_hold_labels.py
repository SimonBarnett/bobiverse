#!/usr/bin/env python3
"""FR #9082: open PRs must not carry issues-only hold / on-hold labels.

EXIT 1 when any open non-draft PR in the fixture list has label ``hold`` or
``on-hold``. Gate work by holding the **issue**, not the PR.

Offline: set ``JEEVES_PR_HOLD_LABELS_FIXTURE`` to a JSON pull list (GitHub
``/pulls`` shape) or ``{"repo": "owner/name", "pulls": [...]}``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from _common import EXIT_FINDING, EXIT_OK, run_check


def _ensure_common() -> None:
    from _common import ensure_script_dir_on_path

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


def _label_names(pr: dict) -> list[str]:
    raw = pr.get("labels") or []
    out: list[str] = []
    for x in raw:
        if isinstance(x, dict):
            name = str(x.get("name") or "").strip()
        else:
            name = str(x).strip()
        if name:
            out.append(name)
    return out


def check(args):
    _ensure_common()
    import gitclaim as gc

    fixture = (os.environ.get("JEEVES_PR_HOLD_LABELS_FIXTURE") or "").strip()
    if not fixture:
        return (
            {
                "ok": True,
                "skipped": "no_fixture",
                "findings": [],
                "bad": [],
                "hint": (
                    "set JEEVES_PR_HOLD_LABELS_FIXTURE to a JSON pull list "
                    "(open pulls) to detect hold/on-hold on PRs"
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
                "bad": [],
                "path_fixture": fixture,
            },
            EXIT_FINDING,
        )

    bad: list[dict[str, Any]] = []
    for pr in pulls if isinstance(pulls, list) else []:
        if not isinstance(pr, dict):
            continue
        if pr.get("draft") is True:
            continue
        state = str(pr.get("state") or "open").lower()
        if state not in {"open", ""}:
            continue
        labs = _label_names(pr)
        hit = gc.pr_forbidden_hold_labels(labs)
        if not hit:
            continue
        num = pr.get("number")
        bad.append(
            {
                "repo": repo
                or str((pr.get("base") or {}).get("repo", {}).get("full_name") or ""),
                "number": num,
                "labels": hit,
                "title": str(pr.get("title") or "")[:120],
            }
        )

    if bad:
        findings = [
            f"PR {row.get('repo')}#{row.get('number')} has issues-only hold label(s): "
            f"{', '.join(row.get('labels') or [])}"
            for row in bad
        ]
        return (
            {
                "ok": False,
                "findings": findings,
                "bad": bad,
                "hint": "remove hold/on-hold from the PR; hold the linked issue instead (FR #9082)",
            },
            EXIT_FINDING,
        )

    return (
        {
            "ok": True,
            "findings": [],
            "bad": [],
            "checked": len(pulls) if isinstance(pulls, list) else 0,
        },
        EXIT_OK,
    )


if __name__ == "__main__":
    raise SystemExit(run_check("pr_hold_labels", __doc__, check))
