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
    # FR #9557: monitor hosts may point at the chair digest (UNC / shared home)
    # via JEEVES_MONITOR_DIGEST_HOME before the seat-local BOB_DIGEST_HOME.
    for key in ("JEEVES_MONITOR_DIGEST_HOME", "BOB_DIGEST_HOME"):
        override = env.get(key)
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

DEFAULT_LIVE_REPORT_URL = "https://bob.ntsa.uk/bob/v1/report"
LIVE_REPORT_USER_AGENT = "Bobiverse-jeeves-monitor/1.0"
LIVE_REPORT_MAX_AGE_SEC = 900  # align with stale_digest default


def live_report_url(env: Optional[dict] = None) -> str:
    env = os.environ if env is None else env
    for key in ("BOB_MONITOR_REPORT_URL", "BOB_DIGEST_URL"):
        raw = str(env.get(key) or "").strip()
        if raw:
            return raw
    return DEFAULT_LIVE_REPORT_URL


def probe_live_report(
    url: str | None = None,
    timeout: float = 12.0,
    env: Optional[dict] = None,
) -> dict[str, Any]:
    """GET public fleet report; always return status metadata (FR #10106)."""
    import urllib.error
    import urllib.request

    target = (url or live_report_url(env)).strip()
    out: dict[str, Any] = {
        "url": target,
        "status": 0,
        "doc": None,
        "error": "",
    }
    if not target:
        out["error"] = "empty_url"
        return out
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
            out["status"] = int(getattr(resp, "status", 200) or 200)
        doc = json.loads(raw or "{}")
        if isinstance(doc, dict):
            out["doc"] = doc
        else:
            out["error"] = "not_json_object"
    except urllib.error.HTTPError as exc:
        out["status"] = int(exc.code)
        out["error"] = f"HTTPError:{exc.code}"
    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        out["error"] = type(exc).__name__
    return out


def fetch_live_report(
    url: str | None = None,
    timeout: float = 12.0,
    env: Optional[dict] = None,
) -> dict[str, Any] | None:
    """GET public fleet report JSON. Returns None on any failure (FR #8579)."""
    return probe_live_report(url=url, timeout=timeout, env=env).get("doc")


def live_report_gateway_down(
    url: str | None = None,
    *,
    timeout: float = 12.0,
    env: Optional[dict] = None,
) -> dict[str, Any]:
    """True when public /bob/v1/report is 502-class or missing JSON (FR #10107)."""
    probe = probe_live_report(url=url, timeout=timeout, env=env)
    status = int(probe.get("status") or 0)
    down = status in (502, 503, 504) or (
        probe.get("doc") is None and status >= 500
    )
    probe["gateway_down"] = down
    return probe


def seat_agent_kind(seat: dict) -> str:
    """Digest/worker row agent kind (grok, cursor, opencode, ...)."""
    for key in ("kind", "agent", "agent_kind", "seat_kind"):
        raw = str((seat or {}).get(key) or "").strip().lower()
        if raw:
            return raw
    model = str((seat or {}).get("model") or "").strip().lower()
    if model.startswith("opencode") or "/opencode" in model:
        return "opencode"
    return ""


def is_opencode_seat(seat: dict) -> bool:
    return seat_agent_kind(seat) == "opencode"


def inbound_transcript_fallback(
    chair: Path,
    digest: Path,
    *,
    max_age_sec: float = 7200.0,
) -> dict[str, Any] | None:
    """Inbound shop-wire tail when live /report is down (FR #10106)."""
    try:
        import inbound_transcript as it
    except ImportError:
        return None
    home = it.resolve_monitor_ear_home(chair, digest)
    if home is None:
        return None
    summary = it.summarize_inbound_monitor_fallback(home, max_age_sec=max_age_sec)
    if not summary.get("wire_events") and not summary.get("disk_giveups"):
        if int(summary.get("lines") or 0) == 0:
            return None
    summary["ear_home"] = str(home)
    summary["fallback"] = "inbound_transcript"
    return summary


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


def _load_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _queue_bucket_len(doc: dict[str, Any] | None, name: str) -> int:
    if not isinstance(doc, dict):
        return 0
    raw = doc.get(name)
    if isinstance(raw, list):
        return len(raw)
    if isinstance(raw, dict):
        return len(raw)
    return 0


def _report_queue_bucket_len(report: dict[str, Any] | None, name: str) -> int:
    if not isinstance(report, dict):
        return 0
    queue = report.get("queue")
    if not isinstance(queue, dict):
        return 0
    return _queue_bucket_len(queue, name)


def _local_digest_worker_nicks(digest: Path) -> set[str]:
    doc = _load_json_file(Path(digest) / "digest.json") or {}
    nicks: set[str] = set()
    machines = doc.get("machines")
    if not isinstance(machines, dict):
        return nicks
    for mid, ent in machines.items():
        if not isinstance(ent, dict):
            continue
        for key in ("workers", "worker_list"):
            raw = ent.get(key)
            if isinstance(raw, dict):
                rows = list(raw.values())
            elif isinstance(raw, list):
                rows = raw
            else:
                continue
            for w in rows:
                if not isinstance(w, dict):
                    continue
                nick = str(w.get("nick") or "").strip().lower()
                if not nick:
                    pid = str(w.get("pid") or "").strip()
                    if pid:
                        nick = f"{mid}-{pid}".lower()
                if nick:
                    nicks.add(nick)
    return nicks


def _report_doing_nicks(report: dict[str, Any] | None) -> set[str]:
    """Seat nicks that look busy/doing on the live report (FR #9557)."""
    out: set[str] = set()
    if not isinstance(report, dict):
        return out
    machines = report.get("machines")
    if not isinstance(machines, dict):
        return out
    for mid, ent in machines.items():
        if not isinstance(ent, dict):
            continue
        for key in ("workers", "worker_list"):
            raw = ent.get(key)
            if isinstance(raw, dict):
                rows = [(pid, w) for pid, w in raw.items()]
            elif isinstance(raw, list):
                rows = [(None, w) for w in raw]
            else:
                continue
            for pid, w in rows:
                if not isinstance(w, dict):
                    continue
                state = str(w.get("state") or w.get("status") or "").strip().lower()
                work = str(w.get("work") or w.get("working_on") or "").strip()
                busy = state in {"doing", "running", "busy", "working"} or bool(work)
                if not busy:
                    continue
                nick = str(w.get("nick") or "").strip().lower()
                if not nick and pid is not None:
                    nick = f"{mid}-{pid}".lower()
                if nick:
                    out.add(nick)
    # Accepted queue holders are also "doing" for monitor purposes.
    queue = report.get("queue") if isinstance(report.get("queue"), dict) else {}
    for row in queue.get("accepted") or []:
        if not isinstance(row, dict):
            continue
        nick = str(
            row.get("nick") or row.get("accepted_by") or row.get("offered_to") or ""
        ).strip().lower()
        if nick:
            out.add(nick)
    return out


def local_idle_contradicted_by_live(
    idle_nicks: list[str] | tuple[str, ...] | set[str],
    report: dict[str, Any] | None,
    *,
    max_age_sec: float = LIVE_REPORT_MAX_AGE_SEC,
) -> set[str]:
    """FR #9849: local idle nicks that a fresh live /report shows as doing/accepted.

    Returns lowercased nick keys. Empty when the report is missing/stale or no
    overlap. Used so local idle+offerable ghosts do not EXIT 1 / !assign-storm
    when the live chair already has those seats busy.
    """
    if not live_report_is_fresh(report, max_age_sec=max_age_sec):
        return set()
    doing = _report_doing_nicks(report)
    if not doing:
        return set()
    out: set[str] = set()
    for raw in idle_nicks or []:
        key = str(raw or "").strip().lower()
        if key and key in doing:
            out.add(key)
    return out


def local_ops_stale_vs_live_report(
    chair: Path,
    digest: Path,
    report: dict[str, Any] | None,
    *,
    max_age_sec: float = LIVE_REPORT_MAX_AGE_SEC,
) -> str:
    """FR #9557: reason when local ops home is empty/stale vs a fresh live report.

    Returns '' when local looks authoritative (or report is not fresh). Non-chair
    hosts often have an empty ``~/.jeeves`` / ``~/.bobiverse`` that still has a
    ``queue.json`` file, so missing-queue alone (FR #8866) is not enough.
    """
    if not live_report_is_fresh(report, max_age_sec=max_age_sec):
        return ""
    assert report is not None
    chair = Path(chair)
    digest = Path(digest)
    qpath = resolve_queue_path(chair, digest)
    local_q = _load_json_file(qpath) if qpath.is_file() else None
    local_unacc = _queue_bucket_len(local_q, "unaccepted")
    local_acc = _queue_bucket_len(local_q, "accepted")
    live_unacc = _report_queue_bucket_len(report, "unaccepted")
    live_acc = _report_queue_bucket_len(report, "accepted")
    if qpath.is_file() and local_unacc == 0 and local_acc == 0 and (live_unacc > 0 or live_acc > 0):
        return "empty_local_queue"
    if not qpath.is_file() and (live_unacc > 0 or live_acc > 0):
        return "missing_local_queue"
    dig_path = digest / "digest.json"
    local_nicks = _local_digest_worker_nicks(digest) if dig_path.is_file() else set()
    doing = _report_doing_nicks(report)
    if doing and not dig_path.is_file():
        return "missing_local_digest"
    # Live ACC/doing seats absent from local digest → local paint is wrong only
    # when the local home itself is empty/thin (FR #9557 empty ~/.jeeves class).
    # Do NOT trip on live_acc > local_acc alone: a healthy chair/local test queue
    # with unaccepted rows is still authoritative even when the live report has
    # extra ACC seats (MRB #9566: that branch poisoned idle_seats unit tests and
    # would hijack non-empty locals whenever the fleet had more ACC).
    missing = {n for n in doing if n not in local_nicks}
    if missing and (
        not dig_path.is_file() or local_unacc + local_acc == 0 or len(local_nicks) == 0
    ):
        return "seat_state_mismatch"
    return ""


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
