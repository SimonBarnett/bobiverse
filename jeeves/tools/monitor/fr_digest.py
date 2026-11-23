#!/usr/bin/env python3
"""Token-free fr_digest check (FR #8849 / BOB-G).

EXIT 1 when an offered or accepted child still Depends-on a queue row that
carries both labels ``fr-digest`` and ``hold`` (chair missed BOB-G1). Distinct
from the plain depends_on OPEN check. No GitHub token: a depend that is not in
the local queue is unknown and does not alarm.

Soft-ok (exit 0):
* no held-digest miss
* live homes (no ``--chair-home``) while BOB-G is not on tip
  (no ``common/scripts/fr_digest_gate.py`` and no ``bob_g1_skip_held_digest``
  in ``common/scripts/gitclaim.py``)
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
    is_digest_row,
    queue_bucket_rows,
    resolve_homes,
    resolve_queue_path,
    run_check,
)

_DEPENDS_LINE = re.compile(r"(?im)^\s*Depends-on:\s*(.+)$")
_REF = re.compile(r"([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)|#(\d+)")
_NONE = re.compile(r"^\(?none\)?$|^-$", re.I)


def _walk_repo_root() -> Path | None:
    cur = Path(__file__).resolve().parent
    for _ in range(8):
        if (cur / "common" / "scripts" / "gitclaim.py").is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def product_on_tip() -> bool:
    root = _walk_repo_root()
    if root is None:
        return False
    if (root / "common" / "scripts" / "fr_digest_gate.py").is_file():
        return True
    gitclaim = root / "common" / "scripts" / "gitclaim.py"
    try:
        text = gitclaim.read_text(encoding="utf-8")
    except OSError:
        return False
    return "bob_g1_skip_held_digest" in text


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


def _key(repo: str, number: int | None) -> str:
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


def _labels(row: dict) -> set[str]:
    raw = row.get("labels") or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    names: set[str] = set()
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, str):
            names.add(item.strip().lower())
        elif isinstance(item, dict):
            names.add(str(item.get("name") or "").strip().lower())
    return names


def held_digest(row: dict) -> bool:
    """Held digest: Digest flag (BOB-G3) plus ``hold`` (BOB-G1)."""
    names = _labels(row)
    if "hold" not in names and "on-hold" not in names:
        return False
    return is_digest_row(row) or "fr-digest" in names or "digest" in names


def _offered_or_accepted(row: dict, bucket: str) -> bool:
    if bucket in ("accepted", "offered"):
        return True
    return bool(str(row.get("offered_to") or "").strip())


def _index(queue: dict) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for bucket in ("unaccepted", "accepted", "offered", "done"):
        for row in queue_bucket_rows(queue, bucket):
            key = _key(_row_repo(row), _row_number(row))
            if key and key not in found:
                found[key] = row
    return found


def check(args):
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
            {"ok": True, "soft_ok": "no_fr_digest_rows", "findings": [], "violations": []},
            EXIT_OK,
        )
    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
    if not isinstance(queue, dict):
        return (
            {"ok": True, "soft_ok": "no_fr_digest_rows", "findings": [], "violations": []},
            EXIT_OK,
        )
    index = _index(queue)
    findings: list[str] = []
    violations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in ("offered", "accepted", "unaccepted"):
        for row in queue_bucket_rows(queue, bucket):
            repo = _row_repo(row)
            ident = _key(repo, _row_number(row)) or "?"
            if ident in seen:
                continue
            if not _offered_or_accepted(row, bucket):
                continue
            body = str(row.get("body") or row.get("issue_body") or "")
            refs = parse_depends(body, repo)
            held = []
            for ref_repo, number in refs:
                dep = index.get(_key(ref_repo, number))
                if dep is None or not held_digest(dep):
                    continue
                held.append(_key(ref_repo, number))
            if not held:
                continue
            seen.add(ident)
            violations.append({"row": ident, "bucket": bucket, "held_digest": held})
            findings.append(
                f"offered/accepted {ident} depends on held fr-digest {', '.join(held)}"
            )
    ok = not findings
    return (
        {
            "ok": ok,
            "soft_ok": "" if not ok else "fr_digest_clear",
            "findings": findings,
            "violations": violations,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "fr_digest",
        "Child offered while Depends-on digest is fr-digest+hold (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
