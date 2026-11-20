#!/usr/bin/env python3
"""Open skill receipts without a harvest/* promote PR (FR #1729 / post-#1682 offer path)."""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, queue_bucket_rows, resolve_homes, resolve_queue_path, run_check

DEFAULT_REPO = "SimonBarnett/bobiverse"
DEFAULT_THRESHOLD = 15
HARVEST_TITLE_RE = re.compile(r"(?i)^(harvest|skill)\b")
PROMOTE_TITLE_RE = re.compile(
    r"(?i)(?:^harvest[\s(:])|(?:\bskill[- ]?promote\b)|(?:\bconsolidate\b.*\bskill\b)"
)


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _label_names(labels) -> tuple[str, ...]:
    out: list[str] = []
    for lab in labels or ():
        if isinstance(lab, dict):
            name = lab.get("name") or lab.get("Name") or ""
        else:
            name = str(lab)
        name = str(name).strip()
        if name:
            out.append(name)
    return tuple(out)


def draft_skill_promote_age_s() -> float:
    """Hours a focused draft via-intake+skill leaflet may sit before EXIT 1 (FR #8477)."""
    raw = (os.environ.get("BOB_DRAFT_SKILL_PROMOTE_AGE_H") or "").strip()
    if not raw:
        return 6.0 * 3600.0
    try:
        return max(0.0, float(raw)) * 3600.0
    except ValueError:
        return 6.0 * 3600.0


def _parse_github_time(value: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime

        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def aged_draft_skill_leaflets(prs, *, now: float, max_age_s: float) -> list:
    """Draft skill leaflets older than max_age_s. Receipt titles are ignored."""
    import gitclaim

    out = []
    for pr in prs or []:
        if not isinstance(pr, dict) or pr.get("draft") is not True:
            continue
        labels = _label_names(pr.get("labels"))
        if not gitclaim.is_draft_skill_leaflet(
            title=str(pr.get("title") or ""),
            body=str(pr.get("body") or ""),
            labels=labels,
        ):
            continue
        created = _parse_github_time(str(pr.get("created_at") or ""))
        if created is None:
            continue
        if now - created >= max_age_s:
            out.append(pr)
    return out


def skill_promote_threshold() -> int:
    raw = (os.environ.get("BOB_SKILL_PROMOTE_THRESHOLD") or "").strip()
    if not raw:
        return DEFAULT_THRESHOLD
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_THRESHOLD


def is_skill_receipt(*, title: str = "", labels=(), body: str = "") -> bool:
    """Post-#1682: label:skill or harvest:/skill: title are offerable promote receipts."""
    labs = {str(x).strip().lower() for x in _label_names(labels)}
    if "skill" in labs:
        return True
    if HARVEST_TITLE_RE.match((title or "").strip()):
        return True
    return False


def is_promote_pr(pr: dict) -> bool:
    """True for open harvest/* skill-book promote PRs (offer-all path)."""
    if not isinstance(pr, dict):
        return False
    head = pr.get("head") or {}
    ref = ""
    if isinstance(head, dict):
        ref = str(head.get("ref") or "")
    elif isinstance(head, str):
        ref = head
    if ref.startswith("harvest/") or ref.startswith("refs/heads/harvest/"):
        return True
    title = str(pr.get("title") or "")
    if PROMOTE_TITLE_RE.search(title):
        return True
    return False


def _row_is_skill_fr(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    task = str(row.get("task") or row.get("type") or "").strip().upper()
    if task and task not in {"FR", "PR", "FIX", "BUILD"}:
        # still allow unlabeled queue rows that look like skill receipts
        pass
    title = str(row.get("title") or row.get("line") or "")
    labels = row.get("labels") or ()
    return is_skill_receipt(title=title, labels=labels, body=str(row.get("body") or ""))


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
    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    queue = _load_json(qpath) if qpath.is_file() else {}
    unaccepted = queue_bucket_rows(queue or {}, "unaccepted")
    accepted = queue_bucket_rows(queue or {}, "accepted")
    queued_skill = [r for r in (unaccepted + accepted) if _row_is_skill_fr(r)]
    thr = skill_promote_threshold()
    repo = (os.environ.get("BOB_SKILL_PROMOTE_REPO") or DEFAULT_REPO).strip() or DEFAULT_REPO
    notes = [
        f"threshold={thr} (BOB_SKILL_PROMOTE_THRESHOLD)",
        "post-#1682: skill/harvest receipts are offerable FRs; workers open harvest/* promote PRs",
        f"repo={repo}",
    ]
    findings: list[str] = []
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    skill_count = None
    promote_pr = False
    open_skill_without_promote_pr = None

    if token:
        try:
            issues, prs = _fetch_open_lists(repo, token)
            receipts = [
                i
                for i in issues
                if isinstance(i, dict)
                and not i.get("pull_request")
                and is_skill_receipt(
                    title=str(i.get("title") or ""),
                    body=str(i.get("body") or ""),
                    labels=_label_names(i.get("labels")),
                )
            ]
            skill_count = len(receipts)
            promote_pr = any(is_promote_pr(p) for p in prs if isinstance(p, dict))
            if skill_count >= thr and not promote_pr and not queued_skill:
                open_skill_without_promote_pr = 1
                findings.append(
                    f"open_skill_without_promote_pr: skill_receipts={skill_count} "
                    f"(>= {thr}) and no open harvest/* promote PR and no queued skill FR"
                )
                notes.append(
                    "remediation: seats should ACK skill/harvest FR offers and open one "
                    "harvest/* consolidate PR per skill book (FR #1684); do not GIVEUP"
                )
            elif skill_count >= thr and promote_pr:
                open_skill_without_promote_pr = 0
                notes.append(
                    f"skill_receipts={skill_count} but harvest/* promote PR open (awaiting MRB)"
                )
            elif skill_count >= thr and queued_skill:
                open_skill_without_promote_pr = 0
                notes.append(
                    f"skill_receipts={skill_count} queued_skill_fr="
                    f"{queued_skill[0].get('id') or queued_skill[0].get('title')} "
                    "(offer path in progress)"
                )
            else:
                open_skill_without_promote_pr = 0
                notes.append(
                    f"skill_receipts={skill_count} below threshold or covered"
                )
            aged = aged_draft_skill_leaflets(
                prs, now=time.time(), max_age_s=draft_skill_promote_age_s()
            )
            if aged:
                nums = ",".join(str(p.get("number")) for p in aged[:12])
                findings.append(
                    f"draft_skill_unpromoted: {len(aged)} draft via-intake+skill "
                    f"leaflet(s) older than BOB_DRAFT_SKILL_PROMOTE_AGE_H "
                    f"with no ready_for_review ({nums})"
                )
                notes.append(
                    "operator fallback: gh pr ready <n> and retitle to "
                    "lesson(<book>): so resync can offer MRB (FR #8477). "
                    "Do not mark DONE/PASS receipt drafts ready."
                )
        except Exception as exc:  # noqa: BLE001
            notes.append(f"github fetch failed: {exc}")
            if not queued_skill:
                findings.append(
                    "open_skill_without_promote_pr: unknown (github fetch failed) "
                    "and no queued skill FR"
                )
    else:
        notes.append("no GITHUB_TOKEN/GH_TOKEN; queue-only probe")
        if queued_skill:
            notes.append(
                f"queued_skill_fr={len(queued_skill)} (offer path has in-flight skill work)"
            )
        else:
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
            "queued_skill_fr_count": len(queued_skill),
            "open_skill_without_promote_pr": open_skill_without_promote_pr,
            "notes": notes,
            "findings": findings,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "skill_promote_backlog",
        "Open skill/harvest receipts without harvest/* promote PR (exit 0/1/2; FR #1729)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
