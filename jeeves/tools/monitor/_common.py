"""Shared JSON one-liner + exit codes for Jeeves monitor scripts (FR #787)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_ERROR = 2


def _is_ephemeral_test_home(path: Path) -> bool:
    """Refuse pytest/tmpdir overrides left in the agent process env (maintenance #2412).

    A leaked ``BOB_DIGEST_HOME`` under ``pytest-of-*`` makes monitor/heal look at an
    empty scratch tree and either false-ok or false-stale while the live chair is fine.
    """
    try:
        parts = {p.lower() for p in Path(path).resolve().parts}
    except OSError:
        parts = {p.lower() for p in Path(path).parts}
    joined = "/".join(Path(path).parts).lower().replace("\\", "/")
    if "pytest-of-" in joined or "/pytest-" in joined or "\\pytest-" in joined.lower():
        return True
    if "pytest-current" in parts:
        return True
    return False


def chair_home(env: Optional[dict] = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("JEEVES_HOME") or env.get("BOB_JEEVES_HOME")
    if override:
        cand = Path(override)
        if not _is_ephemeral_test_home(cand):
            return cand
    return Path(env.get("USERPROFILE") or Path.home()) / ".jeeves"


def digest_home(env: Optional[dict] = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("BOB_DIGEST_HOME")
    if override:
        cand = Path(override)
        if not _is_ephemeral_test_home(cand):
            return cand
    return Path(env.get("USERPROFILE") or Path.home()) / ".bobiverse"


def emit(payload: dict[str, Any], code: int) -> int:
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stdout.flush()
    return code


def build_parser(name: str, description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=name, description=description)
    p.add_argument("--help-exit0", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--dry-run", action="store_true", help="offline: emit ok JSON and exit 0 (no live probes)")
    p.add_argument("--chair-home", default="", help="override ~/.jeeves")
    p.add_argument("--digest-home", default="", help="override ~/.bobiverse")
    return p


def run_check(
    name: str,
    description: str,
    check: Callable[[argparse.Namespace], tuple[dict[str, Any], int]],
    argv: Optional[list[str]] = None,
) -> int:
    p = build_parser(name, description)
    args = p.parse_args(argv)
    if args.dry_run:
        return emit(
            {
                "check": name,
                "ok": True,
                "dry_run": True,
                "findings": [],
            },
            EXIT_OK,
        )
    try:
        payload, code = check(args)
        payload.setdefault("check", name)
        payload.setdefault("dry_run", False)
        return emit(payload, code)
    except Exception as e:
        return emit(
            {
                "check": name,
                "ok": False,
                "dry_run": False,
                "error": f"{type(e).__name__}: {e}",
                "findings": [str(e)],
            },
            EXIT_ERROR,
        )


def resolve_homes(args: argparse.Namespace) -> tuple[Path, Path]:
    ch = Path(args.chair_home) if args.chair_home else chair_home()
    dh = Path(args.digest_home) if args.digest_home else digest_home()
    return ch, dh


def ops_home(chair: Path, digest: Path) -> Path:
    """FR #1043 / MRB #1234: best-effort ops root when queue+focus share a home.

    Prefer the home that has ``queue.json`` (authoritative). Do not let a lone
    ``focus.json`` on chair hide a live ``queue.json`` under digest.
    """
    chair = Path(chair)
    digest = Path(digest)
    if (chair / "queue.json").is_file():
        return chair
    if (digest / "queue.json").is_file():
        return digest
    if (chair / "focus.json").is_file():
        return chair
    if (digest / "focus.json").is_file():
        return digest
    return chair


def resolve_queue_path(chair: Path, digest: Path) -> Path:
    """Per-file resolve: chair queue wins if present, else digest (MRB #1234)."""
    chair = Path(chair)
    digest = Path(digest)
    if (chair / "queue.json").is_file():
        return chair / "queue.json"
    if (digest / "queue.json").is_file():
        return digest / "queue.json"
    return ops_home(chair, digest) / "queue.json"


def resolve_focus_path(chair: Path, digest: Path) -> Path:
    """Per-file resolve: chair focus wins if present, else digest (MRB #1234)."""
    chair = Path(chair)
    digest = Path(digest)
    if (chair / "focus.json").is_file():
        return chair / "focus.json"
    if (digest / "focus.json").is_file():
        return digest / "focus.json"
    return ops_home(chair, digest) / "focus.json"


def iter_worker_entries(machines: object) -> list[dict[str, Any]]:
    """Yield worker dicts from digest ``machines`` (pid-keyed dict or list)."""
    out: list[dict[str, Any]] = []
    if not isinstance(machines, dict):
        return out
    for mid, m in machines.items():
        if not isinstance(m, dict):
            continue
        workers = m.get("workers")
        if isinstance(workers, dict):
            items = workers.items()
            for pid, w in items:
                if isinstance(w, dict):
                    row = dict(w)
                    row.setdefault("machine", mid)
                    row.setdefault("pid", str(pid))
                    if not row.get("nick"):
                        row["nick"] = f"{mid}-{pid}"
                    out.append(row)
        elif isinstance(workers, list):
            for w in workers:
                if isinstance(w, dict):
                    row = dict(w)
                    row.setdefault("machine", mid)
                    out.append(row)
        # optional chair export: worker_list
        wlist = m.get("worker_list")
        if isinstance(wlist, list):
            for w in wlist:
                if isinstance(w, dict):
                    row = dict(w)
                    row.setdefault("machine", mid)
                    out.append(row)
    return out


def queue_bucket_rows(queue: object, *keys: str) -> list[dict[str, Any]]:
    """Rows from named queue.json buckets (list or dict values)."""
    out: list[dict[str, Any]] = []
    if not isinstance(queue, dict):
        return out
    for key in keys:
        v = queue.get(key)
        if isinstance(v, list):
            out.extend([r for r in v if isinstance(r, dict)])
        elif isinstance(v, dict):
            out.extend([r for r in v.values() if isinstance(r, dict)])
    return out


def row_task(row: dict) -> str:
    return str(row.get("task") or row.get("kind") or row.get("type") or "").upper()


def row_has_pull_url(row: dict) -> bool:
    for k in ("url", "pull_url", "pr_url"):
        u = str(row.get(k) or "")
        if "/pull/" in u:
            return True
    return bool(str(row.get("pr_id") or row.get("pr") or "").strip())
