"""FR #7997: one OpenCode data directory per seat, and startup lock policy.

Two ``opencode run`` processes must not share ``opencode.db``. This module
prints the per-seat paths and copies ``auth.json`` from the shared store
into that directory. It does not print file contents.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

LOCK_CUES = ("database is locked", "sqlite_busy", "database is busy")
STARTUP_CUES = ("unexpected error",)
RATE_CUES = (
    "payment required",
    "too many requests",
    "rate limit",
    "rolling limit",
    "free usage limit",
    "subscribe to opencode go",
)
DEFAULT_LOCK_RETRIES = 3


def _safe_tag(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")[:80]


def seat_tag(env: dict[str, str] | None = None) -> str:
    env = env if env is not None else dict(os.environ)
    nick = str(env.get("BOB_NICK") or "").strip()
    pid = str(env.get("BOB_WORKER_PID") or os.getpid()).strip()
    raw = nick or ("seat-" + pid)
    if nick and pid and pid not in nick:
        raw = nick + "-" + pid
    tag = _safe_tag(raw) or "seat"
    return tag


def seat_paths(env: dict[str, str] | None = None) -> tuple[Path, Path, Path]:
    """Return ``(xdg_data_home, opencode_data_dir, opencode_db)``."""
    env = env if env is not None else dict(os.environ)
    custom = str(env.get("BOB_OPENCODE_SEAT_DATA_ROOT") or "").strip()
    if custom:
        base = Path(custom)
    else:
        local = str(env.get("LOCALAPPDATA") or "").strip()
        if not local:
            local = str(Path.home() / "AppData" / "Local")
        base = Path(local) / "Bobiverse" / "worker" / "opencode-data"
    root = base / seat_tag(env)
    data = root / "opencode"
    return root, data, data / "opencode.db"


def fallback_seat_paths(
    env: dict[str, str] | None = None,
    *,
    unique: str | None = None,
) -> tuple[Path, Path, Path]:
    """Unique per-seat paths when ``prepare`` fails (FR #8033).

    Never returns the shared default store. ``unique`` is a short suffix
    (tests pass a fixed token; the launch wrapper uses a GUID fragment).
    """
    env = env if env is not None else dict(os.environ)
    custom = str(env.get("BOB_OPENCODE_SEAT_DATA_ROOT") or "").strip()
    if custom:
        base = Path(custom)
    else:
        local = str(env.get("LOCALAPPDATA") or "").strip()
        if not local:
            local = str(Path.home() / "AppData" / "Local")
        base = Path(local) / "Bobiverse" / "worker" / "opencode-data"
    tag = seat_tag(env)
    suffix = _safe_tag(str(unique or "")) or "fb"
    root = base / (tag + "-" + suffix)
    data = root / "opencode"
    return root, data, data / "opencode.db"


def shared_auth_candidates(env: dict[str, str] | None = None) -> list[Path]:
    env = env if env is not None else dict(os.environ)
    home = Path(str(env.get("USERPROFILE") or Path.home()))
    out = [home / ".local" / "share" / "opencode" / "auth.json"]
    appdata = str(env.get("APPDATA") or "").strip()
    if appdata:
        out.append(Path(appdata) / "opencode" / "auth.json")
    xdg = str(env.get("XDG_DATA_HOME") or "").strip()
    if xdg and "opencode-data" not in xdg.replace("/", "\\").lower():
        out.insert(0, Path(xdg) / "opencode" / "auth.json")
    return out


def prepare_seat_data(env: dict[str, str] | None = None) -> tuple[Path, Path, Path]:
    env = env if env is not None else dict(os.environ)
    root, data, db = seat_paths(env)
    data.mkdir(parents=True, exist_ok=True)
    dest = data / "auth.json"
    if not dest.is_file():
        for src in shared_auth_candidates(env):
            if src.is_file() and src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
                break
    return root, data, db


def classify_startup(
    text: str,
    *,
    exit_code: int | None,
    attempt: int,
    max_retries: int = DEFAULT_LOCK_RETRIES,
    done: bool = False,
) -> str:
    """``retry``, ``giveup``, or ``continue`` for one finished ``opencode run``.

    FR #8147: ``exit_code`` may be ``None`` (the run's exit code was unknown or
    empty) and is treated as unknown, not as a crash. ``done`` is True when the
    job's outbox already carries a terminal line (``DONE``/``FAIL``/``GIVEUP``):
    a finished job is never re-classified as a startup failure.
    """
    if done:
        return "continue"
    code: int | None = None
    if exit_code is not None:
        try:
            code = int(exit_code)
        except (TypeError, ValueError):
            code = None
    if code == 0:
        return "continue"
    low = (text or "").lower()
    if any(c in low for c in RATE_CUES):
        return "continue"
    locked = any(c in low for c in LOCK_CUES)
    if locked and int(attempt) < int(max_retries):
        return "retry"
    if locked or any(c in low for c in STARTUP_CUES):
        return "giveup"
    return "continue"


def _cmd_prepare() -> int:
    root, data, db = prepare_seat_data()
    sys.stdout.write("XDG_DATA_HOME=%s\n" % root)
    sys.stdout.write("BOB_OPENCODE_DATA_DIR=%s\n" % data)
    sys.stdout.write("OPENCODE_DB=%s\n" % db)
    return 0


def _cmd_classify(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="classify")
    p.add_argument("--attempt", type=int, default=0)
    p.add_argument("--max", type=int, default=DEFAULT_LOCK_RETRIES)
    # FR #8147: the wrapper may pass an empty/null exit code (or omit --exit).
    # nargs="?" accepts a missing/empty value as unknown instead of argparse
    # dying with "argument --exit: expected one argument".
    p.add_argument("--exit", dest="exit_code", nargs="?", default=None)
    p.add_argument("--done", action="store_true", default=False)
    args = p.parse_args(argv)
    text = sys.stdin.read()
    sys.stdout.write(
        classify_startup(
            text,
            exit_code=args.exit_code,
            attempt=args.attempt,
            max_retries=args.max,
            done=args.done,
        )
        + "\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write("usage: opencode_seat_isolate.py prepare | classify\n")
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "prepare":
        return _cmd_prepare()
    if cmd == "classify":
        return _cmd_classify(rest)
    sys.stderr.write("unknown command\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
