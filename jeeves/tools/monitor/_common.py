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


def chair_home(env: Optional[dict] = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("JEEVES_HOME") or env.get("BOB_JEEVES_HOME")
    if override:
        return Path(override)
    return Path(env.get("USERPROFILE") or Path.home()) / ".jeeves"


def digest_home(env: Optional[dict] = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("BOB_DIGEST_HOME")
    if override:
        return Path(override)
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
