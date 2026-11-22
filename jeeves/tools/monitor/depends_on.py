#!/usr/bin/env python3
"""Token-free Depends-on check (FR #8848 / BOB-D).

EXIT 1 when an offered or accepted queue row has a body ``Depends-on:`` ref
that is still OPEN in this queue (chair missed BOB-D3). Distinct from the hold
label and from ``fr_digest``. No GitHub token: a ref that is not in the local
queue is unknown and does not alarm.

Soft-ok (exit 0):
* no Depends-on rows
* live homes (no ``--chair-home``) while the product skip is not on tip
  (no ``common/scripts/depends_on_parse.py`` and no ``bob_d3_skip_open`` in
  ``common/scripts/gitclaim.py``)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from _common import (
    EXIT_FINDING,
    EXIT_OK,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

_DEPENDS_LINE = re.compile(r"(?im)^\s*Depends-on:\s*(.+)$")
_REF = re.compile(
    r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)|#(\d+)"
)
_NONE = re.compile(r"^\(?none\)?$|^-$", re.I)
_SKIP_STATES = {"skipped", "skip", "depends_skipped"}


def _walk_repo_root() -> Path | None:
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        marker = cur / "common" / "scripts" / "gitclaim.py"
        if marker.is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def product_on_tip() -> bool:
    """True once BOB-D skip/parse has landed on this tree."""
    root = _walk_repo_root()
    if root is None:
        return False
    if (root / "common" / "scripts" / "depends_on_parse.py").is_file():
        return True
    gitclaim = root / "common" / "scripts" / "gitclaim.py"
    try:
        text = gitclaim.read_text(encoding="utf-8")
    except OSError:
        return False
    return "bob_d3_skip_open" in text


def _row_repo(row: dict) -> str:
    return str(row.get("repo") or row.get("owner_repo") or "").strip()


def _row_number(row: dict) -> int | None:
    raw = row.get("number")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    ident = str(row.get("id") or raw or "")
    match = re.search(r"(\d+)", ident)
    return int(match.group(1)) if match else None


def _row_key(repo: str, number: int | None) -> str:
    if not repo or number is None:
        return ""
    return f"{repo}#{number}"


def parse_depends(body: str, default_repo: str) -> list[tuple[str, int]]:
    refs: list[tuple[str, int]] = []
    for line in _DEPENDS_LINE.findall(body or ""):
        text = line.strip()
        if _NONE.match(text):
            continue
        for match in _REF.finditer(text):
            if match.group(1):
                refs.append((match.group(1), int(match.group(2))))
            elif default_repo:
                refs.append((default_repo, int(match.group(3))))
    return refs


def _is_skipped(row: dict) -> bool:
    if row.get("depends_skipped") or row.get("skip_reason"):
        return True
    for key in ("status", "state", "queue_state"):
        if str(row.get(key) or "").strip().lower() in _SKIP_STATES:
            return True
    return False


def _is_offered_or_accepted(row: dict, bucket: str) -> bool:
    if bucket in ("accepted", "offered"):
        return True
    return bool(str(row.get("offered_to") or "").strip())


def _open_keys(queue: dict) -> set[str]:
    keys: set[str] = set()
    for bucket in ("unaccepted", "accepted", "offered"):
        for row in queue_bucket_rows(queue, bucket):
            state = str(row.get("state") or row.get("issue_state") or "").lower()
            if state in ("closed", "done"):
                continue
            key = _row_key(_row_repo(row), _row_number(row))
            if key:
                keys.add(key)
    return keys


def check(args):
    # Live monitor does not pass --chair-home. Until BOB-D is on tip, do not
    # alarm the chair for behaviour the product has not shipped yet.
    if not getattr(args, "chair_home", "") and not product_on_tip():
        return (
            {
                "ok": True,
                "soft_ok": "product_not_on_tip",
                "findings": [],
                "violations": [],
            },
            EXIT_OK,
        )
    chair, digest = resolve_homes(args)
    qpath = resolve_queue_path(chair, digest)
    if not qpath.is_file():
        return (
            {
                "ok": True,
                "soft_ok": "no_depends_on_rows",
                "findings": [],
                "violations": [],
            },
            EXIT_OK,
        )
    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
    if not isinstance(queue, dict):
        return (
            {
                "ok": True,
                "soft_ok": "no_depends_on_rows",
                "findings": [],
                "violations": [],
            },
            EXIT_OK,
        )
    open_keys = _open_keys(queue)
    findings: list[str] = []
    violations: list[dict[str, Any]] = []
    saw_depends = False
    seen: set[str] = set()
    for bucket in ("offered", "accepted", "unaccepted"):
        for row in queue_bucket_rows(queue, bucket):
            repo = _row_repo(row)
            number = _row_number(row)
            ident = _row_key(repo, number) or "?"
            if ident in seen and bucket == "unaccepted":
                continue
            body = str(row.get("body") or row.get("issue_body") or "")
            refs = parse_depends(body, repo)
            extra = row.get("depends_on")
            if isinstance(extra, list):
                for item in extra:
                    text = str(item)
                    refs.extend(parse_depends(f"Depends-on: {text}", repo))
            if not refs:
                continue
            saw_depends = True
            if _is_skipped(row):
                continue
            if not _is_offered_or_accepted(row, bucket):
                continue
            open_refs = [f"{r}#{n}" for r, n in refs if f"{r}#{n}" in open_keys]
            if not open_refs:
                continue
            seen.add(ident)
            violations.append({"row": ident, "bucket": bucket, "open": open_refs})
            findings.append(
                f"offered/accepted {ident} depends on OPEN {', '.join(open_refs)}"
            )
    if not saw_depends:
        return (
            {
                "ok": True,
                "soft_ok": "no_depends_on_rows",
                "findings": [],
                "violations": [],
            },
            EXIT_OK,
        )
    ok = not findings
    return (
        {
            "ok": ok,
            "soft_ok": "" if not ok else "depends_clear",
            "findings": findings,
            "violations": violations,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "depends_on",
        "Offered/accepted rows with Depends-on still OPEN (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
