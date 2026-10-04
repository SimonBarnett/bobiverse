#!/usr/bin/env python3
"""FR #1520: alert when focus.items keys sit under an already-focused repo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import EXIT_FINDING, EXIT_OK, resolve_focus_path, resolve_homes, run_check


def _short(repo: str) -> str:
    return (repo or "").rsplit("/", 1)[-1].lower()


def _repo_match(key: str, repo: str) -> bool:
    k, r = (key or "").strip().lower(), (repo or "").strip().lower()
    if not k or not r:
        return False
    if k == r:
        return True
    if "/" not in k:
        return k == _short(r)
    return "/" not in r and _short(k) == r


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def check(args):
    chair, digest = resolve_homes(args)
    findings = []
    remediation = []
    focus_path = resolve_focus_path(chair, digest)
    focus = _load_json(focus_path) if focus_path.is_file() else None
    redundant: list[str] = []
    if isinstance(focus, dict):
        repos = focus.get("repos") if isinstance(focus.get("repos"), dict) else {}
        items = focus.get("items") if isinstance(focus.get("items"), dict) else {}
        for key, meta in items.items():
            item_repo = ""
            if isinstance(meta, dict):
                item_repo = str(meta.get("repo") or "").strip()
            if not item_repo and "#" in str(key):
                item_repo = str(key).split("#", 1)[0].strip()
            if item_repo and any(
                _repo_match(rk, item_repo) or _repo_match(item_repo, rk) for rk in repos
            ):
                redundant.append(str(key))
    if redundant:
        findings.append(
            f"focus.items has {len(redundant)} key(s) under already-focused repo(s) "
            f"(FR #1520 per-repo policy): {', '.join(sorted(redundant)[:8])}"
        )
        remediation.append(
            "!unfocus <owner/repo#N> for each redundant item "
            "(or wait for !resync prune_redundant_focus_items); prefer !focus owner/repo"
        )
    ok = not findings
    return (
        {
            "ok": ok,
            "redundant_count": len(redundant),
            "redundant": sorted(redundant),
            "path": str(focus_path),
            "findings": findings,
            "remediation": remediation,
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    return run_check(
        "focus_redundant_items",
        "FR #1520: focus.items under already-focused repos (exit 0/1/2)",
        check,
        argv,
    )


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
