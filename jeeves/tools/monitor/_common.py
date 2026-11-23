"""Shared JSON one-liner + exit codes for Jeeves monitor scripts (FR #787)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

EXIT_OK = 0
EXIT_FINDING = 1
EXIT_ERROR = 2

# BOB-G3 / FR #9108: Digest flag recognition (mirrors gitclaim.digest_issue_reason).
_DIGEST_LABELS = frozenset({"digest", "fr-digest"})
_DIGEST_KIND_RE = re.compile(
    r"(?im)^[^\S\n]*(?:\*{0,2}|`{0,2})Kind(?:\*{0,2}|`{0,2})"
    r"[^\S\n]*:"
    r"(?:\*{0,2}|`{0,2})?"
    r"[^\S\n]*(fr-digest|digest)\b"
)


def is_digest_row(row: dict) -> bool:
    """True for issue FR digests via ``digest``/``fr-digest`` label or Kind: stamp.

    Issues-only. Ignores title. MRB / pull_request-shaped rows are never digests.
    """
    if not isinstance(row, dict):
        return False
    task = str(row.get("task") or "").strip().upper()
    if task and task != "FR":
        return False
    event = str(row.get("event") or "").strip().lower()
    if event == "pull_request":
        return False
    url = str(row.get("url") or "")
    if "/pull/" in url.replace("\\", "/").lower():
        return False
    raw = row.get("labels") or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    names: set[str] = set()
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                names.add(item.strip().lower())
            elif isinstance(item, dict):
                names.add(str(item.get("name") or "").strip().lower())
    if names & _DIGEST_LABELS:
        return True
    body = str(row.get("body") or "")
    return _DIGEST_KIND_RE.search(body) is not None


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


def find_upward_file(
    start: Path,
    *parts: str,
    max_levels: int = 8,
) -> Optional[Path]:
    """Walk ``start`` and ancestors for ``joinpath(*parts)`` without ``parents[N]``.

    FR #8580: a drive-root install (``J:\\tools\\monitor``) has fewer than three
    parents; indexing ``Path.parents[2]`` / ``[3]`` raises ``IndexError`` before
    any candidate is tried. Bound the walk and stop at the filesystem root.
    """
    if not parts:
        return None
    try:
        cur = Path(start).resolve()
    except OSError:
        cur = Path(start)
    for _ in range(int(max_levels) + 1):
        cand = cur.joinpath(*parts)
        try:
            if cand.is_file():
                return cand
        except OSError:
            pass
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def ensure_script_dir_on_path(
    *markers: str,
    start: Optional[Path] = None,
    max_levels: int = 8,
) -> Optional[Path]:
    """Insert the directory that holds the first found marker onto ``sys.path``.

    Tries ``common/scripts/<marker>`` then ``scripts/<marker>`` walking upward
    from ``start`` (default: this package directory).
    """
    here = Path(start) if start is not None else Path(__file__).resolve().parent
    for marker in markers:
        name = str(marker).strip()
        if not name:
            continue
        for rel in (("common", "scripts", name), ("scripts", name)):
            found = find_upward_file(here, *rel, max_levels=max_levels)
            if found is None:
                continue
            scripts = str(found.parent)
            if scripts not in sys.path:
                sys.path.insert(0, scripts)
            return found.parent
    return None


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
# --- FR #8579: non-chair monitor overlay (live /bob/v1/report) -----------------

DEFAULT_LIVE_REPORT_URL = "https://irc.ntsa.uk/bob/v1/report"
LIVE_REPORT_USER_AGENT = "Bobiverse-jeeves-monitor/1.0"
LIVE_REPORT_MAX_AGE_SEC = 900  # align with stale_digest default


def live_report_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    for key in ("BOB_MONITOR_REPORT_URL", "BOB_DIGEST_URL"):
        raw = str(env.get(key) or "").strip()
        if raw:
            return raw
    return DEFAULT_LIVE_REPORT_URL


def fetch_live_report(
    url: str | None = None,
    timeout: float = 12.0,
    env: Optional[dict] = None,
) -> dict[str, Any] | None:
    """GET public fleet report JSON. Returns None on any failure (FR #8579)."""
    import urllib.error
    import urllib.request

    target = (url or live_report_url(env)).strip()
    if not target:
        return None
    try:
        req = urllib.request.Request(
            target,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": LIVE_REPORT_USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
        doc = json.loads(raw or "{}")
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ):
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def report_age_sec(doc: dict[str, Any] | None, *, now: float | None = None) -> float | None:
    """Age of report ``ts`` (ISO-8601) in seconds, or None if unparseable."""
    import time
    from datetime import datetime, timezone

    if not isinstance(doc, dict):
        return None
    ts = doc.get("ts") or doc.get("updated") or doc.get("when")
    if not isinstance(ts, str) or not ts.strip():
        return None
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now_f = float(time.time() if now is None else now)
    return max(0.0, now_f - parsed.timestamp())


def live_report_is_fresh(
    doc: dict[str, Any] | None,
    *,
    max_age_sec: float = LIVE_REPORT_MAX_AGE_SEC,
    now: float | None = None,
) -> bool:
    age = report_age_sec(doc, now=now)
    if age is None:
        return False
    return age <= float(max_age_sec)


def local_queue_absent(chair: Path, digest: Path) -> bool:
    """True when neither chair nor digest home has queue.json (non-chair seat)."""
    return not resolve_queue_path(chair, digest).is_file()


def non_chair_overlay(
    chair: Path,
    digest: Path,
    *,
    require_missing_queue: bool = False,
    report: dict[str, Any] | None = None,
    fetch: bool = True,
    max_age_sec: float = LIVE_REPORT_MAX_AGE_SEC,
) -> dict[str, Any] | None:
    """Return overlay meta when live /report is fresh and this host looks non-chair.

    Non-chair = local ``queue.json`` missing (typical worker/monitor box). When
    ``require_missing_queue`` is False, freshness alone is enough for soft-pass
    of local-only probes (health services / stale local digest) so operators are
    not flooded with false ionos-outage cues (FR #8579).
    """
    if require_missing_queue and not local_queue_absent(chair, digest):
        return None
    doc = report
    if doc is None and fetch:
        doc = fetch_live_report()
    if not live_report_is_fresh(doc, max_age_sec=max_age_sec):
        return None
    assert doc is not None
    age = report_age_sec(doc)
    queue = doc.get("queue") if isinstance(doc.get("queue"), dict) else {}
    unacc = queue.get("unaccepted")
    acc = queue.get("accepted")
    unacc_n = len(unacc) if isinstance(unacc, list) else (
        len(unacc) if isinstance(unacc, dict) else None
    )
    acc_n = len(acc) if isinstance(acc, list) else (
        len(acc) if isinstance(acc, dict) else None
    )
    return {
        "non_chair_overlay": True,
        "live_report_url": live_report_url(),
        "live_report_ts": doc.get("ts"),
        "live_report_age_sec": int(age) if age is not None else None,
        "live_chair_nick": doc.get("chairNick") or doc.get("chair_nick"),
        "live_queue_unaccepted": unacc_n,
        "live_queue_accepted": acc_n,
        "local_queue_absent": local_queue_absent(chair, digest),
    }
