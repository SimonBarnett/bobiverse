#!/usr/bin/env python3
"""GitHub core rate-limit remaining vs fleet floor (FR #9104).

One-account fleets share a single user OAuth 5k/hr bucket. EXIT 1 when
``resources.core.remaining`` is below the floor (default 500 =
``github_api_budget.BACKOFF_FLOOR``) so ops see which machine is starved.

Live probe uses ``gh api rate_limit`` (does not burn core quota). Tests and
offline seats can set ``BOB_GITHUB_RATE_REMAINING`` / ``BOB_GITHUB_RATE_LIMIT``
or pass ``--remaining`` / ``--limit`` to skip ``gh``.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from typing import Any, Optional

from _common import EXIT_ERROR, EXIT_FINDING, EXIT_OK, build_parser, emit

# Match common/scripts/github_api_budget.BACKOFF_FLOOR (keep local to avoid path deps).
DEFAULT_FLOOR = 500
DEFAULT_LIMIT = 5000


def _machine_id(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    mid = (env.get("BOB_MACHINE_ID") or "").strip().lower()
    if mid:
        return mid
    host = (env.get("COMPUTERNAME") or env.get("HOSTNAME") or "").strip().lower()
    if host:
        return host
    try:
        return socket.gethostname().strip().lower() or "unknown"
    except OSError:
        return "unknown"


def _parse_int(raw: str, default: int) -> int:
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _floor_from_env(env: Optional[dict] = None) -> int:
    env = os.environ if env is None else env
    return max(0, _parse_int(env.get("BOB_GITHUB_RATE_FLOOR") or "", DEFAULT_FLOOR))


def _probe_gh() -> tuple[Optional[int], Optional[int], Optional[int], str]:
    """Return (remaining, limit, reset, error). error empty on success."""
    gh = shutil.which("gh")
    if not gh:
        return None, None, None, "gh not found on PATH"
    try:
        r = subprocess.run(
            [gh, "api", "rate_limit", "--jq", ".resources.core"],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception as e:
        return None, None, None, f"{type(e).__name__}: {e}"
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:240] or f"gh exit {r.returncode}"
        return None, None, None, err
    try:
        doc = json.loads(r.stdout or "{}")
    except json.JSONDecodeError as e:
        return None, None, None, f"JSONDecodeError: {e}"
    if not isinstance(doc, dict):
        return None, None, None, "core resource not an object"
    rem = doc.get("remaining")
    lim = doc.get("limit")
    reset = doc.get("reset")
    try:
        remaining = int(rem) if rem is not None else None
        limit = int(lim) if lim is not None else None
        reset_i = int(reset) if reset is not None else None
    except (TypeError, ValueError):
        return None, None, None, "core remaining/limit/reset not int"
    if remaining is None:
        return None, None, None, "core.remaining missing"
    return remaining, limit, reset_i, ""


def check(args):
    env = os.environ
    machine = _machine_id(env)
    floor = int(getattr(args, "floor", None) or _floor_from_env(env))
    source = "gh"

    remaining: Optional[int] = None
    limit: Optional[int] = DEFAULT_LIMIT
    reset: Optional[int] = None

    if getattr(args, "remaining", None) is not None and str(args.remaining) != "":
        remaining = _parse_int(args.remaining, -1)
        source = "arg"
        if getattr(args, "limit", None) is not None and str(args.limit) != "":
            limit = _parse_int(args.limit, DEFAULT_LIMIT)
    elif env.get("BOB_GITHUB_RATE_REMAINING") not in (None, ""):
        remaining = _parse_int(env["BOB_GITHUB_RATE_REMAINING"], -1)
        source = "env"
        if env.get("BOB_GITHUB_RATE_LIMIT") not in (None, ""):
            limit = _parse_int(env["BOB_GITHUB_RATE_LIMIT"], DEFAULT_LIMIT)
    else:
        remaining, limit, reset, err = _probe_gh()
        if err:
            return (
                {
                    "ok": False,
                    "machine": machine,
                    "floor": floor,
                    "source": source,
                    "error": err,
                    "findings": [f"github_rate_limit probe failed on {machine}: {err}"],
                    "remediation": [
                        "ensure gh is authenticated for this seat",
                        "or set BOB_GITHUB_RATE_REMAINING for offline / test",
                    ],
                },
                EXIT_ERROR,
            )

    assert remaining is not None
    findings: list[str] = []
    remediation: list[str] = []
    if remaining < floor:
        findings.append(
            f"core.remaining={remaining} < floor={floor} on machine={machine} "
            f"(shared user OAuth 5k/hr bucket — FR #9104)"
        )
        remediation.append(
            "pause non-essential gh (search/list); exponential backoff on API rate limit exceeded"
        )
        remediation.append(
            "ops: prefer per-machine fine-grained PAT / GitHub App token "
            "(never commit tokens); chair and seats must not share one user OAuth"
        )
        remediation.append(
            "chair: check_run/check_suite local rate defer returns 204 (FR #9104); "
            "watch stdout for reason=rate deferred"
        )

    ok = not findings
    payload: dict[str, Any] = {
        "ok": ok,
        "machine": machine,
        "remaining": remaining,
        "limit": limit if limit is not None else DEFAULT_LIMIT,
        "floor": floor,
        "reset": reset,
        "source": source,
        "findings": findings,
        "remediation": remediation,
    }
    return payload, EXIT_OK if ok else EXIT_FINDING


def main(argv=None) -> int:
    p = build_parser(
        "github_rate_limit",
        "GitHub core rate-limit remaining vs fleet floor (FR #9104)",
    )
    p.add_argument(
        "--floor",
        default="",
        help=f"finding when remaining < floor (default {DEFAULT_FLOOR} or BOB_GITHUB_RATE_FLOOR)",
    )
    p.add_argument(
        "--remaining",
        default="",
        help="offline: inject core.remaining (skips gh)",
    )
    p.add_argument(
        "--limit",
        default="",
        help="offline: inject core.limit (with --remaining)",
    )
    # Custom parse so --floor/--remaining work with run_check dry-run path.
    args = p.parse_args(argv)
    if args.dry_run:
        return emit(
            {
                "check": "github_rate_limit",
                "ok": True,
                "dry_run": True,
                "findings": [],
            },
            EXIT_OK,
        )
    if args.floor not in (None, ""):
        args.floor = _parse_int(args.floor, DEFAULT_FLOOR)
    else:
        args.floor = _floor_from_env()
    try:
        payload, code = check(args)
        payload.setdefault("check", "github_rate_limit")
        payload.setdefault("dry_run", False)
        return emit(payload, code)
    except Exception as e:
        return emit(
            {
                "check": "github_rate_limit",
                "ok": False,
                "dry_run": False,
                "error": f"{type(e).__name__}: {e}",
                "findings": [str(e)],
            },
            EXIT_ERROR,
        )


if __name__ == "__main__":
    raise SystemExit(main())
