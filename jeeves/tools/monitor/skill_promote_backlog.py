#!/usr/bin/env python3
"""Skill-promote backlog (FR #1682): open skill receipts without a promote PR/row."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, queue_bucket_rows, resolve_homes, resolve_queue_path, run_check


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _ensure_gitclaim():
    here = Path(__file__).resolve().parent
    for cand in (
        here.parents[1] / "scripts",
        here.parents[2] / "common" / "scripts",
        here.parents[1] / "common" / "scripts",
    ):
        if (cand / "gitclaim.py").is_file():
            p = str(cand)
            if p not in sys.path:
                sys.path.insert(0, p)
            break
    import gitclaim  # noqa: WPS433

    return gitclaim


def _gh_get(url: str, token: str):
    hdrs = {"Accept": "application/vnd.github+json", "User-Agent": "bobiverse-monitor"}
    if token:
        hdrs["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_open_lists(repo: str, token: str) -> tuple[list, list]:
    issues: list = []
    prs: list = []
    for page in range(1, 11):
        chunk = _gh_get(
            f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100&page={page}",
            token,
        )
        if not isinstance(chunk, list) or not chunk:
            break
        issues.extend(chunk)
        if len(chunk) < 100:
            break
    for page in range(1, 6):
        chunk = _gh_get(
            f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100&page={page}",
            token,
        )
        if not isinstance(chunk, list) or not chunk:
            break
        prs.extend(chunk)
        if len(chunk) < 100:
            break
    return issues, prs


def check(args):
    gc = _ensure_gitclaim()
    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    queue = _load_json(qpath) if qpath.is_file() else {}
    unaccepted = queue_bucket_rows(queue or {}, "unaccepted")
    accepted = queue_bucket_rows(queue or {}, "accepted")
    queued_promote = [
        r
        for r in (unaccepted + accepted)
        if isinstance(r, dict)
        and (
            gc.row_is_skill_promote(r)
            or gc.issue_is_skill_promote(
                title=str(r.get("title") or ""),
                labels=r.get("labels") or (),
            )
        )
    ]
    thr = gc.skill_promote_threshold()
    notes = [
        f"threshold={thr} (BOB_SKILL_PROMOTE_THRESHOLD)",
        "bare skill/harvest receipts stay SKIP_FR; skill-promote FR is the offerable path (FR #1682)",
    ]
    findings = []
    token = (
        (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    )
    skill_count = None
    promote_pr = False
    promote_issue = False
    open_skill_without_promote_pr = None
    repo = gc.SKILL_PROMOTE_REPO

    if token:
        try:
            issues, prs = _fetch_open_lists(repo, token)
            receipts = [
                i
                for i in issues
                if isinstance(i, dict)
                and not i.get("pull_request")
                and gc.issue_is_skill_receipt(
                    title=str(i.get("title") or ""),
                    body=str(i.get("body") or ""),
                    labels=gc._label_names(i.get("labels")),
                    state=str(i.get("state") or "open"),
                )
            ]
            skill_count = len(receipts)
            promote_pr = any(
                gc.is_skill_promote_pr(
                    title=str(p.get("title") or ""),
                    labels=gc._label_names(p.get("labels")),
                )
                for p in prs
                if isinstance(p, dict)
            )
            promote_issue = any(
                gc.issue_is_skill_promote(
                    title=str(i.get("title") or ""),
                    labels=gc._label_names(i.get("labels")),
                )
                for i in issues
                if isinstance(i, dict) and not i.get("pull_request")
            )
            open_skill_without_promote_pr = int(
                skill_count >= thr and not promote_pr
            )
            if skill_count >= thr and not promote_pr and not queued_promote and not promote_issue:
                findings.append(
                    f"open_skill_without_promote_pr: skill_receipts={skill_count} "
                    f"(>= {thr}) and no skill-promote PR/issue/queue row"
                )
                notes.append(
                    "remediation: open one FR labeled skill-promote (or set GITHUB_TOKEN "
                    "so chair resync can create/enqueue), seat opens harvest/ PR + MRB"
                )
            elif skill_count >= thr and not promote_pr and queued_promote:
                notes.append(
                    f"skill_receipts={skill_count} queued_promote="
                    f"{queued_promote[0].get('id')} (awaiting ACK/PR)"
                )
            elif skill_count >= thr and promote_pr:
                notes.append(
                    f"skill_receipts={skill_count} but promote PR open (awaiting MRB)"
                )
            else:
                notes.append(f"skill_receipts={skill_count} below threshold or covered")
        except Exception as exc:  # noqa: BLE001
            notes.append(f"github fetch failed: {exc}")
            if not queued_promote:
                findings.append(
                    "open_skill_without_promote_pr: unknown (github fetch failed) "
                    "and no skill-promote queue row"
                )
    else:
        notes.append("no GITHUB_TOKEN/GH_TOKEN; queue-only probe")
        if not queued_promote:
            # Soft finding: cannot see GitHub skill count without token.
            notes.append(
                "set GITHUB_TOKEN on the monitor host to compute open_skill_without_promote_pr"
            )

    ok = not findings
    return (
        {
            "ok": ok,
            "ops_home": str(chair if (chair / "queue.json").is_file() else digest),
            "queue_path": str(qpath),
            "skill_count": skill_count,
            "threshold": thr,
            "promote_pr_open": promote_pr,
            "promote_issue_open": promote_issue,
            "queued_promote_count": len(queued_promote),
            "open_skill_without_promote_pr": open_skill_without_promote_pr,
            "notes": notes,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "skill_promote_backlog",
        "Skill/harvest receipt backlog without promote PR (exit 0/1/2; FR #1682)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
