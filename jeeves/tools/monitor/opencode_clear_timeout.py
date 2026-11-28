#!/usr/bin/env python3
"""FR #10040: OpenCode Clear TimeoutExpired plus stale no-ACK."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

FINGERPRINT = "opencode_clear_timeout_no_ack"

_CLEAR = re.compile(
    r"opencode finish: Clear result=(?:failed:TimeoutExpired|skipped:timeout)"
)
_STALE = re.compile(r"relay: stale worktree offer .+no ACK yet", re.I)
_LOG_NAMES = {"stdout.log", "cmd-trace.log", "opencode.log"}


def scan_log(text: str, *, machine: str, nick: str, turns_empty: bool) -> str | None:
    """Return the fingerprint when Clear timed out and no ACK followed."""
    if not text or not turns_empty:
        return None
    if not _CLEAR.search(text) or not _STALE.search(text):
        return None
    return "%s:%s:%s" % (FINGERPRINT, machine, nick)


def _turns_empty(log_path: Path) -> bool:
    turns = log_path.parent / "turns.jsonl"
    if not turns.is_file():
        return True
    try:
        return turns.stat().st_size == 0
    except OSError:
        return True


def _identity(log_path: Path) -> tuple[str, str]:
    for part in reversed(log_path.parts):
        if re.match(r"^[a-z0-9]+-\d+$", part, re.I):
            nick = part
            machine = nick.split("-", 1)[0]
            return machine, nick
    return "local", "seat"


def scan_tree(root: Path) -> list[str]:
    found: list[str] = []
    if not root.is_dir():
        return found
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules"}]
        for name in filenames:
            if name not in _LOG_NAMES and not name.endswith(".log"):
                continue
            seen += 1
            if seen > 400:
                return found
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            machine, nick = _identity(path)
            fp = scan_log(text, machine=machine, nick=nick, turns_empty=_turns_empty(path))
            if fp and fp not in found:
                found.append(fp)
    return found


def check(args) -> tuple[dict, int]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _common import EXIT_FINDING, EXIT_OK, resolve_homes

    fixture = os.environ.get("JEEVES_OPENCODE_CLEAR_FIXTURE") or ""
    roots = []
    if fixture:
        roots.append(Path(fixture))
    else:
        chair, _digest = resolve_homes(args)
        roots.append(chair)
    findings: list[str] = []
    for root in roots:
        for fp in scan_tree(root):
            if fp not in findings:
                findings.append(fp)
    ok = not findings
    return (
        {
            "ok": ok,
            "findings": findings,
            "marker": "fr10040_opencode_clear_timeout",
        },
        EXIT_OK if ok else EXIT_FINDING,
    )


def main(argv=None) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _common import run_check

    return run_check(
        "opencode_clear_timeout",
        "OpenCode Clear TimeoutExpired plus stale no-ACK (FR #10040)",
        check,
        argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
