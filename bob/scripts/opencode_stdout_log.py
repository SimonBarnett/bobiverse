"""FR #8069: per-job OpenCode stdout/stderr log, redacted and capped.

The live console is unchanged. The worker tees capture files here.
``BOB_OPENCODE_STDOUT_LOG=0`` turns the log off.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_COMMON = Path(__file__).resolve().parents[2] / "common" / "scripts"
if str(_COMMON) not in sys.path:
    sys.path.insert(0, str(_COMMON))

from crash_report import redact  # noqa: E402

MAX_BYTES = 20 * 1024 * 1024
KEEP_PER_SEAT = 50
_JOB_RX = re.compile(r"(?i)\b(FR|MRB|UAT|FIX)\s+(\S+?)#(\d+)\b")
_SAFE_RX = re.compile(r"[^A-Za-z0-9._-]+")


def enabled(env: dict | None = None) -> bool:
    env = os.environ if env is None else env
    flag = str(env.get("BOB_OPENCODE_STDOUT_LOG", "1")).strip().lower()
    return flag not in ("0", "false", "off", "no")


def logs_dir(env: dict | None = None) -> Path:
    env = os.environ if env is None else env
    base = str(env.get("LOCALAPPDATA") or "").strip()
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "Bobiverse" / "worker" / "logs" / "opencode"


def _safe(text: str, fallback: str) -> str:
    cleaned = _SAFE_RX.sub("-", str(text or "").strip()).strip("-._")
    return cleaned[:80] or fallback


def parse_job_key(job_key: str) -> tuple[str, str, str]:
    match = _JOB_RX.search(str(job_key or ""))
    if not match:
        return "unknown", "job", "0"
    repo = match.group(2).replace("/", "-")
    return repo, match.group(1).upper(), match.group(3)


def log_file_name(repo: str, kind: str, number: str, seat: str, when: datetime) -> str:
    stamp = when.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s-%s-%s-%s.log" % (
        _safe(repo, "repo"),
        _safe(kind, "job"),
        _safe(number, "0"),
        _safe(seat, "seat"),
        stamp,
    )


def _header(seat: str, model: str, job: str, worktree: str, when: datetime) -> str:
    started = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "seat=%s" % redact(seat or ""),
        "model=%s" % redact(model or ""),
        "job=%s" % redact(job or ""),
        "worktree=%s" % redact(worktree or ""),
        "start=%s" % started,
        "",
    ]
    return "\n".join(lines)


def prune_seat_logs(directory: Path, seat: str, *, keep: int = KEEP_PER_SEAT) -> None:
    """Keep the newest ``keep`` logs whose name contains ``-<seat>-``."""
    token = "-%s-" % _safe(seat, "seat")
    files = [p for p in directory.glob("*.log") if token in p.name]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def open_log(
    *,
    job_key: str,
    seat: str,
    model: str,
    worktree: str,
    env: dict | None = None,
    now: datetime | None = None,
) -> Path | None:
    env = os.environ if env is None else env
    if not enabled(env):
        return None
    when = now or datetime.now(timezone.utc)
    repo, kind, number = parse_job_key(job_key)
    directory = logs_dir(env)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / log_file_name(repo, kind, number, seat, when)
    path.write_text(
        _header(seat, model, job_key, worktree, when),
        encoding="utf-8",
        newline="\n",
    )
    prune_seat_logs(directory, seat)
    return path


def append_text(path: Path | str, text: str, *, max_bytes: int = MAX_BYTES) -> None:
    """Append redacted lines. Stop once the file reaches ``max_bytes``."""
    target = Path(path)
    if not text:
        return
    try:
        size = target.stat().st_size
    except OSError:
        size = 0
    if size >= max_bytes:
        return
    lines = []
    for raw in str(text).splitlines():
        lines.append(redact(raw))
    blob = ("\n".join(lines) + "\n").encode("utf-8", "replace")
    room = max_bytes - size
    truncated = False
    if len(blob) > room:
        blob = blob[: max(0, room - 24)] + b"\n[truncated]\n"
        truncated = True
    with target.open("ab") as handle:
        handle.write(blob)
    if truncated:
        return


def _cmd_open(env: dict) -> int:
    path = open_log(
        job_key=env.get("BOB_OC_LOG_JOB", ""),
        seat=env.get("BOB_OC_LOG_SEAT") or env.get("BOB_NICK") or "",
        model=env.get("BOB_OC_LOG_MODEL") or env.get("BOB_OPENCODE_MODEL") or "",
        worktree=env.get("BOB_OC_LOG_WORKTREE", ""),
        env=env,
    )
    if path is not None:
        sys.stdout.write(str(path))
    return 0


def _cmd_append(argv: list[str], env: dict) -> int:
    if not enabled(env):
        return 0
    if len(argv) < 2:
        return 2
    path, src = argv[0], argv[1]
    try:
        text = Path(src).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    append_text(path, text)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return 2
    cmd, rest = args[0], args[1:]
    env = dict(os.environ)
    if cmd == "open":
        return _cmd_open(env)
    if cmd == "append":
        return _cmd_append(rest, env)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
