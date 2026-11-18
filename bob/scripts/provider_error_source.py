"""FR #8150: pluggable per-seat-kind provider error sources.

OpenCode often writes ``Free usage limit reached`` only to its app log
(``<data>/log/opencode.log``), not to the run's stdout/stderr. The launch
wrapper and seat-start path must treat that log as a first-class fuel
signal so the seat GIVEUPs and ``record-pause`` instead of hanging.

Grok and Cursor register their own sources here; a missing path is a
no-op, never a hard failure.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

# --------------------------------------------------------------------------- paths

def _safe_import_opencode_fuel():
    try:
        import opencode_fuel as of  # type: ignore

        return of
    except Exception:
        here = Path(__file__).resolve().parent
        for folder in (here, here.parent.parent / "common" / "scripts"):
            if folder.is_dir() and str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
        try:
            import opencode_fuel as of  # type: ignore

            return of
        except Exception:
            return None


def _safe_import_seat_isolate():
    try:
        import opencode_seat_isolate as iso  # type: ignore

        return iso
    except Exception:
        here = Path(__file__).resolve().parent
        if str(here) not in sys.path:
            sys.path.insert(0, str(here))
        try:
            import opencode_seat_isolate as iso  # type: ignore

            return iso
        except Exception:
            return None


def opencode_app_log_path(env: dict | None = None) -> Optional[Path]:
    """Per-seat OpenCode app log: ``<BOB_OPENCODE_DATA_DIR>/log/opencode.log``.

    Falls back to the predicted seat data dir from ``opencode_seat_isolate``
    when the env var is not set yet (seat-start, before ``prepare``).
    """
    env = os.environ if env is None else env
    data = str(env.get("BOB_OPENCODE_DATA_DIR") or "").strip()
    if data:
        return Path(data) / "log" / "opencode.log"
    iso = _safe_import_seat_isolate()
    if iso is None:
        return None
    try:
        _root, data_dir, _db = iso.seat_paths(env)
    except Exception:
        return None
    return Path(data_dir) / "log" / "opencode.log"


def grok_unified_log_path(env: dict | None = None) -> Optional[Path]:
    """Grok ``unified.jsonl`` under the agent home (existing FR #3012 path)."""
    env = os.environ if env is None else env
    override = str(env.get("BOB_WORKER_OUT_OF_FUEL_LOG") or "").strip()
    if override:
        return Path(override)
    home = str(env.get("GROK_HOME") or env.get("BOB_GROK_HOME") or "").strip()
    if home:
        return Path(home) / "logs" / "unified.jsonl"
    # Match bob_worker.default_unified_log_path shape when run_dir is unknown.
    local = str(env.get("LOCALAPPDATA") or "").strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "Bobiverse" / "worker" / "logs" / "unified.jsonl"


# --------------------------------------------------------------------------- registry

SourceFn = Callable[[Optional[dict]], Optional[Path]]

PROVIDER_ERROR_SOURCES: dict[str, tuple[SourceFn, ...]] = {
    # OpenCode: app log is the gap #8150 closes; wrapper fuel log remains a
    # secondary source via bob_worker.default_out_of_fuel_log_path.
    "opencode": (opencode_app_log_path,),
    "grok": (grok_unified_log_path,),
    "cursor": (),
}


def provider_error_log_paths(kind: str, env: dict | None = None) -> list[Path]:
    """Ordered log paths for ``kind``. Missing paths are omitted."""
    env = os.environ if env is None else env
    key = (kind or "").strip().lower()
    out: list[Path] = []
    for fn in PROVIDER_ERROR_SOURCES.get(key, ()):
        try:
            p = fn(env)
        except Exception:
            p = None
        if p is not None:
            out.append(Path(p))
    return out


# --------------------------------------------------------------------------- line parse

# key=value OpenCode log (current): timestamp=... level=ERROR run=... message="stream error" ...
_KV_LEVEL_RX = re.compile(r"(?i)(?:^|\s)level=([A-Za-z]+)\b")
# space-separated evidence form: 2026-11-17T20:00:12Z level=ERROR message="stream error" ...
_TS_PREFIX_RX = re.compile(
    r"(?i)^(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+Z)\s+level=(?P<level>[A-Za-z]+)\b"
)
_KV_TS_RX = re.compile(
    r"(?i)(?:^|\s)timestamp=(?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+Z)\b"
)
_RUN_RX = re.compile(r"(?i)(?:^|\s)run=([A-Za-z0-9_-]+)\b")
_STREAM_ERROR_RX = re.compile(r"(?i)stream\s+error")

_FREE_USAGE_RX = re.compile(
    r"(?i)(?:Free\s+usage\s+limit|subscribe\s+to\s+OpenCode\s+Go)"
)


@dataclass(frozen=True)
class ProviderErrorHit:
    reason: str
    line: str
    source: str = "opencode-app-log"
    level: str = "ERROR"
    run_id: str = ""


def _line_level(line: str) -> str:
    m = _TS_PREFIX_RX.match(line or "")
    if m:
        return (m.group("level") or "").upper()
    m = _KV_LEVEL_RX.search(line or "")
    if m:
        return (m.group(1) or "").upper()
    return ""


def _line_run_id(line: str) -> str:
    m = _RUN_RX.search(line or "")
    return (m.group(1) if m else "") or ""


def _parse_line_ts(line: str) -> Optional[float]:
    """Return unix seconds for a log line timestamp, or None."""
    m = _TS_PREFIX_RX.match(line or "")
    raw = m.group("ts") if m else None
    if not raw:
        m2 = _KV_TS_RX.search(line or "")
        raw = m2.group("ts") if m2 else None
    if not raw:
        return None
    try:
        from datetime import datetime, timezone

        text = raw.replace("Z", "+00:00")
        # trim subsecond to fromisoformat-friendly form
        if "." in text:
            head, rest = text.split(".", 1)
            frac = re.match(r"(\d+)", rest)
            tz = rest[len(frac.group(1)) :] if frac else rest
            text = head + "." + (frac.group(1)[:6] if frac else "0") + tz
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def looks_like_provider_refusal_text(text: str) -> bool:
    """True when text matches RATE_LIMIT_PHRASES / free-usage (shared with fuel)."""
    of = _safe_import_opencode_fuel()
    if of is not None:
        try:
            if of.is_free_usage_limit_text(text) or of.looks_like_rate_limit(text):
                return True
        except Exception:
            pass
    if _FREE_USAGE_RX.search(text or ""):
        return True
    low = (text or "").lower()
    for phrase in (
        "too many requests",
        "rate limit",
        "rolling limit",
        "usage balance exhausted",
        "payment required",
    ):
        if phrase in low:
            return True
    return False


def classify_opencode_app_log_line(
    line: str,
    *,
    run_id: str | None = None,
) -> Optional[ProviderErrorHit]:
    """Return a hit only for ERROR-level provider refusals in the OpenCode app log.

    INFO / WARN / DEBUG lines never fire, even when they quote the phrase.
    Tool stdout is not this log; callers must not feed capture files here
    unless they already look like app-log lines.
    """
    text = (line or "").rstrip("\n")
    if not text.strip():
        return None
    level = _line_level(text)
    if level != "ERROR":
        return None
    if not looks_like_provider_refusal_text(text):
        return None
    # Prefer stream-error rows (the live refusal path). Other ERROR rows that
    # already carry a rate/free phrase still count.
    rid = _line_run_id(text)
    if run_id and rid and rid != run_id:
        return None
    reason = (
        "fuel-exhausted:opencode-free"
        if _FREE_USAGE_RX.search(text)
        else "out-of-fuel"
    )
    return ProviderErrorHit(
        reason=reason,
        line=text,
        source="opencode-app-log",
        level=level,
        run_id=rid,
    )


def scan_opencode_app_log(
    path: Path | str | None,
    *,
    since_offset: int = 0,
    since_ts: float | None = None,
    run_id: str | None = None,
    max_bytes: int = 2 * 1024 * 1024,
) -> tuple[int, list[ProviderErrorHit]]:
    """Scan ``path`` for new ERROR provider refusals.

    ``since_offset`` is a byte offset (EOF baseline at run start). ``since_ts``
    drops lines whose timestamp is older (seat-start scan of a reused log).
    Returns ``(new_offset, hits)``.
    """
    if not path:
        return int(since_offset or 0), []
    p = Path(path)
    if not p.is_file():
        return int(since_offset or 0), []
    try:
        size = p.stat().st_size
    except OSError:
        return int(since_offset or 0), []
    offset = max(0, int(since_offset or 0))
    if size < offset:
        offset = 0
    if size == offset and since_ts is None:
        return offset, []
    # Seat-start full-file scan: read a trailing window only.
    read_from = offset
    if since_ts is not None and offset == 0 and size > max_bytes:
        read_from = max(0, size - max_bytes)
    try:
        with p.open("r", encoding="utf-8", errors="replace") as fh:
            if read_from:
                fh.seek(read_from)
            chunk = fh.read()
            new_offset = fh.tell()
    except OSError:
        return offset, []
    hits: list[ProviderErrorHit] = []
    for ln in chunk.splitlines():
        if since_ts is not None:
            ts = _parse_line_ts(ln)
            if ts is not None and ts < float(since_ts):
                continue
        hit = classify_opencode_app_log_line(ln, run_id=run_id)
        if hit is not None:
            hits.append(hit)
    return new_offset, hits


def apply_seat_start_opencode_app_log_pause(
    *,
    env: dict | None = None,
    state_dir: Path | str | None = None,
    model_id: str = "",
    lookback_s: float = 300.0,
    now: float | None = None,
) -> Optional[ProviderErrorHit]:
    """Seat-start: recent ERROR free-usage in the app log -> record-pause.

    Same path as mid-job #8026 / #7952 fallback: once paused, model selection
    skips the exhausted model.
    """
    env = os.environ if env is None else env
    now = time.time() if now is None else float(now)
    path = opencode_app_log_path(env)
    _offset, hits = scan_opencode_app_log(
        path, since_offset=0, since_ts=now - float(lookback_s)
    )
    if not hits:
        return None
    hit = hits[-1]
    of = _safe_import_opencode_fuel()
    if of is None:
        return hit
    mid = str(model_id or env.get("BOB_OPENCODE_MODEL") or "").strip()
    if not mid:
        # Pause the free pool id so free seats fall through.
        mid = "opencode-free"
    if state_dir is None:
        state_dir = Path(
            str(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        ) / "Bobiverse" / "worker" / "state"
    try:
        of.record_opencode_pause(state_dir, mid, hit.line, now=now)
    except Exception:
        pass
    return hit


# --------------------------------------------------------------------------- CLI (launch wrapper)

def _cmd_peek(argv: list[str]) -> int:
    """``peek <path> <offset> [--run-id ID]`` -> ``OK <newoffset>`` or ``HIT <reason> <newoffset>``."""
    p = argparse.ArgumentParser(prog="peek")
    p.add_argument("path")
    p.add_argument("offset", type=int, nargs="?", default=0)
    p.add_argument("--run-id", default="")
    args = p.parse_args(argv)
    new_off, hits = scan_opencode_app_log(
        args.path,
        since_offset=args.offset,
        run_id=(args.run_id or None),
    )
    if hits:
        sys.stdout.write("HIT %s %d\n" % (hits[0].reason, new_off))
        return 0
    sys.stdout.write("OK %d\n" % new_off)
    return 0


def _cmd_paths(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="paths")
    p.add_argument("--kind", default="opencode")
    args = p.parse_args(argv)
    for path in provider_error_log_paths(args.kind):
        sys.stdout.write("%s\n" % path)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write(
            "usage: provider_error_source.py peek <path> <offset> [--run-id ID]\n"
            "       provider_error_source.py paths [--kind opencode|grok|cursor]\n"
        )
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "peek":
        return _cmd_peek(rest)
    if cmd == "paths":
        return _cmd_paths(rest)
    sys.stderr.write("unknown command\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
