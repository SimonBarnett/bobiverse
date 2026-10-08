"""Hours webhook store: agents POST partial work-time entries for timesheet drafting (FR #3450).

Synchronous store under digest home ``hours/``. No auth (clear-text by design); protection is
schema validation, body size caps, per-source rate limits, and credential-field rejection.
Nothing here writes to Priority.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

HOURS_PATH = "/bob/v1/hours"
LONDON = ZoneInfo("Europe/London")
OPEN_TIMEOUT_ENV = "BOB_HOURS_OPEN_TIMEOUT_MIN"
DEFAULT_OPEN_TIMEOUT_MIN = 120
MAX_HOURS_BYTES = 64 * 1024
HOURS_RATE_ENV = "BOB_HOURS_RATE_PER_MIN"
DEFAULT_HOURS_RATE_PER_MIN = 60

_ID_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_IDEMP_SAFE = re.compile(r"^[A-Za-z0-9._:@-]{1,128}$")
_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_STATUS = frozenset({"open", "closed", "auto_closed", "withdrawn"})
_BILLABLE = frozenset({"Y", "N", ""})
_CREDENTIAL_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "authorization",
        "auth",
        "bearer",
        "private_key",
        "client_secret",
        "sasl",
        "nickserv",
        "github.token",
        "x-bob-secret",
    }
)

_ACTION_RE = re.compile(
    r"^/bob/v1/hours/([A-Za-z0-9._-]{1,64})/(heartbeat|close|withdraw)$"
)


def hours_rate_per_min() -> int:
    try:
        return max(1, int(os.environ.get(HOURS_RATE_ENV) or DEFAULT_HOURS_RATE_PER_MIN))
    except ValueError:
        return DEFAULT_HOURS_RATE_PER_MIN


def open_timeout_minutes() -> int:
    try:
        return max(1, int(os.environ.get(OPEN_TIMEOUT_ENV) or DEFAULT_OPEN_TIMEOUT_MIN))
    except ValueError:
        return DEFAULT_OPEN_TIMEOUT_MIN


def hours_root(home: Path) -> Path:
    root = Path(home) / "hours"
    (root / "entries").mkdir(parents=True, exist_ok=True)
    (root / "idempotency").mkdir(parents=True, exist_ok=True)
    return root


def is_hours_route(route: str) -> bool:
    r = (route or "").split("?", 1)[0]
    if r == HOURS_PATH:
        return True
    if r in (HOURS_PATH + "/summary", HOURS_PATH + "/export"):
        return True
    if _ACTION_RE.match(r):
        return True
    return False


def is_hours_post_route(route: str) -> bool:
    r = (route or "").split("?", 1)[0]
    if r == HOURS_PATH:
        return True
    return bool(_ACTION_RE.match(r))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso(raw: str) -> datetime | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _london_day(dt: datetime) -> date:
    return dt.astimezone(LONDON).date()


def _parse_day(raw: str) -> date | None:
    s = str(raw or "").strip()
    if not _DATE.match(s):
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _json_error(code: int, error: str) -> tuple[int, bytes]:
    return code, json.dumps({"error": error}, separators=(",", ":")).encode("utf-8")


def _json_ok(code: int, obj: Any) -> tuple[int, bytes]:
    return code, json.dumps(obj, separators=(",", ":")).encode("utf-8")


def contains_credential_fields(obj: Any, *, _depth: int = 0) -> bool:
    """True when any dict key looks like a credential field (never log bodies)."""
    if _depth > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = str(k).strip().lower().replace("-", "_")
            if key in _CREDENTIAL_KEYS or key.endswith("_password") or key.endswith("_token"):
                return True
            if contains_credential_fields(v, _depth=_depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if contains_credential_fields(item, _depth=_depth + 1):
                return True
    return False


def _entry_path(home: Path, entry_id: str) -> Path:
    return hours_root(home) / "entries" / f"{entry_id}.json"


def _idem_path(home: Path, key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._@:-]", "_", key)[:128]
    return hours_root(home) / "idempotency" / f"{safe}.json"


def load_entry(home: Path, entry_id: str) -> dict[str, Any] | None:
    eid = str(entry_id or "").strip()
    if not eid or not _ID_SAFE.fullmatch(eid):
        return None
    path = _entry_path(home, eid)
    if not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def _write_entry(home: Path, entry: dict[str, Any]) -> None:
    eid = str(entry["id"])
    path = _entry_path(home, eid)
    tmp = path.with_suffix(".tmp")
    data = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def _find_by_idempotency(home: Path, key: str) -> dict[str, Any] | None:
    path = _idem_path(home, key)
    if not path.is_file():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    return load_entry(home, str(meta.get("id") or ""))


def _set_idempotency(home: Path, key: str, entry_id: str) -> None:
    path = _idem_path(home, key)
    path.write_text(
        json.dumps({"id": entry_id, "key": key}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _derive_duration(start: datetime, end: datetime | None) -> int | None:
    if end is None:
        return None
    mins = int((end - start).total_seconds() // 60)
    return max(0, mins)


def validate_create_payload(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    if contains_credential_fields(payload):
        return "credential_field_rejected", {}
    idem = str(payload.get("idempotency_key") or "").strip()
    if not idem or not _IDEMP_SAFE.fullmatch(idem):
        return "bad_idempotency_key", {}
    agent = str(payload.get("agent") or "").strip()
    if not agent or len(agent) > 128:
        return "bad_agent", {}
    on_behalf = str(payload.get("on_behalf_of") or "").strip()
    if not on_behalf or len(on_behalf) > 64:
        return "bad_on_behalf_of", {}
    start = _parse_iso(str(payload.get("start") or ""))
    if start is None:
        return "bad_start", {}
    end_raw = payload.get("end")
    end: datetime | None = None
    if end_raw not in (None, ""):
        end = _parse_iso(str(end_raw))
        if end is None:
            return "bad_end", {}
        if end < start:
            return "bad_end_before_start", {}
    customer = str(payload.get("customer") or "").strip()
    if customer and not _SLUG.fullmatch(customer):
        return "bad_customer", {}
    project = str(payload.get("project") or "").strip()
    if project and not _SLUG.fullmatch(project):
        return "bad_project", {}
    repo_url = str(payload.get("repo_url") or "").strip()
    if repo_url and not (repo_url.startswith("https://") or repo_url.startswith("http://")):
        return "bad_repo_url", {}
    if len(repo_url) > 512:
        return "bad_repo_url", {}
    priority_project = str(payload.get("priority_project") or "").strip()
    if len(priority_project) > 64:
        return "bad_priority_project", {}
    wbs = str(payload.get("wbs") or "").strip()
    if len(wbs) > 64:
        return "bad_wbs", {}
    tickets = payload.get("tickets")
    if tickets is None:
        tickets = []
    if not isinstance(tickets, list):
        return "bad_tickets", {}
    clean_tickets: list[str] = []
    for t in tickets:
        s = str(t).strip()
        if not s or len(s) > 256:
            return "bad_tickets", {}
        clean_tickets.append(s)
    billable = str(payload.get("billable_hint") or "").strip().upper()
    if billable not in _BILLABLE:
        return "bad_billable_hint", {}
    description = str(payload.get("description") or "").strip()
    if len(description) > 4000:
        return "bad_description", {}
    evidence = payload.get("evidence")
    if evidence is None:
        evidence = []
    if not isinstance(evidence, list):
        return "bad_evidence", {}
    clean_evidence: list[str] = []
    for e in evidence:
        s = str(e).strip()
        if not s or len(s) > 512:
            return "bad_evidence", {}
        clean_evidence.append(s)
    supersedes = str(payload.get("supersedes") or "").strip()
    if supersedes and not _ID_SAFE.fullmatch(supersedes):
        return "bad_supersedes", {}
    source = str(payload.get("source") or "").strip()
    if len(source) > 128:
        return "bad_source", {}
    duration = payload.get("duration_minutes")
    if duration is not None and duration != "":
        try:
            duration_i = int(duration)
        except (TypeError, ValueError):
            return "bad_duration_minutes", {}
        if duration_i < 0 or duration_i > 24 * 60 * 14:
            return "bad_duration_minutes", {}
    else:
        duration_i = _derive_duration(start, end)

    status = "closed" if end is not None else "open"
    now = _utc_now()
    norm = {
        "idempotency_key": idem,
        "agent": agent,
        "on_behalf_of": on_behalf,
        "start": _iso(start),
        "end": _iso(end) if end else None,
        "duration_minutes": duration_i,
        "customer": customer,
        "project": project,
        "repo_url": repo_url,
        "priority_project": priority_project,
        "wbs": wbs,
        "tickets": clean_tickets,
        "billable_hint": billable,
        "description": description,
        "evidence": clean_evidence,
        "status": status,
        "supersedes": supersedes or None,
        "source": source or "cloud",
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "last_heartbeat": _iso(now),
    }
    return None, norm


def create_entry(home: Path, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    err, norm = validate_create_payload(payload)
    if err:
        return 400, {"error": err}
    existing = _find_by_idempotency(home, norm["idempotency_key"])
    if existing is not None:
        return 200, existing
    eid = f"h_{uuid.uuid4().hex[:16]}"
    entry = dict(norm)
    entry["id"] = eid
    if entry.get("supersedes"):
        old = load_entry(home, entry["supersedes"])
        if old is not None and old.get("status") not in ("withdrawn",):
            # Keep for audit; mark withdrawn so it leaves totals.
            old = dict(old)
            old["status"] = "withdrawn"
            old["updated_at"] = entry["updated_at"]
            _write_entry(home, old)
    _write_entry(home, entry)
    _set_idempotency(home, entry["idempotency_key"], eid)
    return 201, entry


def _maybe_auto_close(home: Path, entry: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if entry.get("status") != "open":
        return entry
    hb = _parse_iso(str(entry.get("last_heartbeat") or entry.get("start") or ""))
    if hb is None:
        return entry
    when = now or _utc_now()
    timeout = timedelta(minutes=open_timeout_minutes())
    if when - hb <= timeout:
        return entry
    closed = dict(entry)
    closed["end"] = _iso(hb)
    closed["status"] = "auto_closed"
    closed["duration_minutes"] = _derive_duration(
        _parse_iso(str(entry.get("start") or "")) or hb, hb
    )
    closed["updated_at"] = _iso(when)
    _write_entry(home, closed)
    return closed


def heartbeat_entry(home: Path, entry_id: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    payload = payload or {}
    if contains_credential_fields(payload):
        return 400, {"error": "credential_field_rejected"}
    entry = load_entry(home, entry_id)
    if entry is None:
        return 404, {"error": "not_found"}
    entry = _maybe_auto_close(home, entry)
    if entry.get("status") != "open":
        return 409, {"error": "not_open", "entry": entry}
    now = _utc_now()
    entry = dict(entry)
    entry["last_heartbeat"] = _iso(now)
    entry["updated_at"] = _iso(now)
    _write_entry(home, entry)
    return 200, entry


def close_entry(home: Path, entry_id: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    payload = payload or {}
    if contains_credential_fields(payload):
        return 400, {"error": "credential_field_rejected"}
    entry = load_entry(home, entry_id)
    if entry is None:
        return 404, {"error": "not_found"}
    entry = _maybe_auto_close(home, entry)
    if entry.get("status") != "open":
        return 409, {"error": "not_open", "entry": entry}
    end = _parse_iso(str(payload.get("end") or "")) or _utc_now()
    start = _parse_iso(str(entry.get("start") or ""))
    if start and end < start:
        return 400, {"error": "bad_end_before_start"}
    entry = dict(entry)
    entry["end"] = _iso(end)
    entry["status"] = "closed"
    entry["duration_minutes"] = _derive_duration(start or end, end)
    if "description" in payload and payload.get("description") is not None:
        desc = str(payload.get("description") or "").strip()
        if len(desc) > 4000:
            return 400, {"error": "bad_description"}
        entry["description"] = desc
    now = _utc_now()
    entry["updated_at"] = _iso(now)
    entry["last_heartbeat"] = _iso(now)
    _write_entry(home, entry)
    return 200, entry


def withdraw_entry(home: Path, entry_id: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    payload = payload or {}
    if contains_credential_fields(payload):
        return 400, {"error": "credential_field_rejected"}
    entry = load_entry(home, entry_id)
    if entry is None:
        return 404, {"error": "not_found"}
    if entry.get("status") == "withdrawn":
        return 200, entry
    entry = dict(entry)
    entry["status"] = "withdrawn"
    entry["updated_at"] = _iso(_utc_now())
    _write_entry(home, entry)
    return 200, entry


def list_entries(home: Path) -> list[dict[str, Any]]:
    root = hours_root(home) / "entries"
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict) and obj.get("id"):
            out.append(_maybe_auto_close(home, obj))
    return out


def _entry_in_range(entry: dict[str, Any], day_from: date | None, day_to: date | None) -> bool:
    start = _parse_iso(str(entry.get("start") or ""))
    if start is None:
        return False
    d = _london_day(start)
    if day_from and d < day_from:
        return False
    if day_to and d > day_to:
        return False
    return True


def filter_entries(
    entries: list[dict[str, Any]],
    *,
    user: str = "",
    agent: str = "",
    customer: str = "",
    project: str = "",
    ticket: str = "",
    status: str = "",
    day_from: date | None = None,
    day_to: date | None = None,
) -> list[dict[str, Any]]:
    user = (user or "").strip()
    agent = (agent or "").strip()
    customer = (customer or "").strip()
    project = (project or "").strip()
    ticket = (ticket or "").strip()
    status = (status or "").strip()
    out: list[dict[str, Any]] = []
    for e in entries:
        if user and str(e.get("on_behalf_of") or "") != user:
            continue
        if agent and str(e.get("agent") or "") != agent:
            continue
        if customer and str(e.get("customer") or "") != customer:
            continue
        if project and str(e.get("project") or "") != project:
            continue
        if status and str(e.get("status") or "") != status:
            continue
        if ticket:
            tickets = e.get("tickets") if isinstance(e.get("tickets"), list) else []
            if ticket not in [str(t) for t in tickets]:
                continue
        if not _entry_in_range(e, day_from, day_to):
            continue
        out.append(e)
    return out


def _parse_query(path: str) -> dict[str, str]:
    qs = parse_qs(urlparse(path).query, keep_blank_values=True)
    return {k: (v[0] if v else "") for k, v in qs.items()}


def _active_for_totals(entry: dict[str, Any]) -> bool:
    return str(entry.get("status") or "") in ("open", "closed", "auto_closed")


def _interval(entry: dict[str, Any]) -> tuple[datetime, datetime] | None:
    start = _parse_iso(str(entry.get("start") or ""))
    if start is None:
        return None
    end = _parse_iso(str(entry.get("end") or ""))
    if end is None:
        end = _parse_iso(str(entry.get("last_heartbeat") or "")) or start
    if end < start:
        end = start
    return start, end


def deoverlap_minutes(intervals: list[tuple[datetime, datetime]]) -> int:
    if not intervals:
        return 0
    ordered = sorted(intervals, key=lambda x: x[0])
    merged: list[list[datetime]] = [[ordered[0][0], ordered[0][1]]]
    for s, e in ordered[1:]:
        if s <= merged[-1][1]:
            if e > merged[-1][1]:
                merged[-1][1] = e
        else:
            merged.append([s, e])
    total = 0
    for s, e in merged:
        total += int((e - s).total_seconds() // 60)
    return max(0, total)


def find_overlaps(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """List pairwise overlaps for active entries sharing on_behalf_of."""
    by_user: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if not _active_for_totals(e):
            continue
        iv = _interval(e)
        if iv is None:
            continue
        by_user.setdefault(str(e.get("on_behalf_of") or ""), []).append(e)
    overlaps: list[dict[str, Any]] = []
    for user, group in by_user.items():
        for i in range(len(group)):
            a = group[i]
            ia = _interval(a)
            if ia is None:
                continue
            for j in range(i + 1, len(group)):
                b = group[j]
                ib = _interval(b)
                if ib is None:
                    continue
                start = max(ia[0], ib[0])
                end = min(ia[1], ib[1])
                if end <= start:
                    continue
                mins = int((end - start).total_seconds() // 60)
                if mins <= 0:
                    continue
                overlaps.append(
                    {
                        "on_behalf_of": user,
                        "a": a.get("id"),
                        "b": b.get("id"),
                        "minutes": mins,
                        "start": _iso(start),
                        "end": _iso(end),
                    }
                )
    return overlaps


def build_summary(
    entries: list[dict[str, Any]],
    *,
    user: str = "",
    day_from: date | None = None,
    day_to: date | None = None,
) -> dict[str, Any]:
    filtered = filter_entries(
        entries, user=user, day_from=day_from, day_to=day_to
    )
    days: dict[str, dict[str, Any]] = {}
    for e in filtered:
        start = _parse_iso(str(e.get("start") or ""))
        if start is None:
            continue
        day_key = _london_day(start).isoformat()
        bucket = days.setdefault(
            day_key,
            {
                "date": day_key,
                "raw_minutes": 0,
                "deoverlapped_minutes": 0,
                "groups": {},
                "open_or_auto": [],
                "_intervals": [],
            },
        )
        if e.get("status") in ("open", "auto_closed"):
            bucket["open_or_auto"].append(e.get("id"))
        if not _active_for_totals(e):
            continue
        mins = e.get("duration_minutes")
        if mins is None:
            iv = _interval(e)
            mins = int((iv[1] - iv[0]).total_seconds() // 60) if iv else 0
        bucket["raw_minutes"] += int(mins or 0)
        iv = _interval(e)
        if iv:
            bucket["_intervals"].append(iv)
        cust = str(e.get("customer") or "") or "(none)"
        proj = str(e.get("project") or "") or "(none)"
        wbs = str(e.get("wbs") or "") or "(none)"
        tickets = e.get("tickets") if isinstance(e.get("tickets"), list) else []
        ticket_key = ",".join(str(t) for t in tickets) if tickets else "(none)"
        gkey = f"{cust}|{proj}|{wbs}|{ticket_key}"
        g = bucket["groups"].setdefault(
            gkey,
            {
                "customer": cust,
                "project": proj,
                "wbs": wbs,
                "tickets": list(tickets),
                "raw_minutes": 0,
                "count": 0,
            },
        )
        g["raw_minutes"] += int(mins or 0)
        g["count"] += 1

    day_list = []
    for day_key in sorted(days):
        b = days[day_key]
        b["deoverlapped_minutes"] = deoverlap_minutes(b.pop("_intervals"))
        b["groups"] = list(b["groups"].values())
        day_list.append(b)
    return {
        "user": user or None,
        "from": day_from.isoformat() if day_from else None,
        "to": day_to.isoformat() if day_to else None,
        "days": day_list,
        "overlaps": find_overlaps(filtered),
    }


def export_entries(
    entries: list[dict[str, Any]],
    *,
    fmt: str = "json",
) -> tuple[str, str]:
    """Return (content_type, body_text)."""
    fmt = (fmt or "json").strip().lower()
    if fmt == "csv":
        buf = io.StringIO()
        fields = [
            "id",
            "idempotency_key",
            "agent",
            "on_behalf_of",
            "start",
            "end",
            "duration_minutes",
            "customer",
            "project",
            "repo_url",
            "priority_project",
            "wbs",
            "tickets",
            "billable_hint",
            "description",
            "status",
            "source",
            "created_at",
            "updated_at",
        ]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for e in entries:
            row = {k: e.get(k) for k in fields}
            tickets = e.get("tickets")
            row["tickets"] = "|".join(str(t) for t in tickets) if isinstance(tickets, list) else ""
            w.writerow(row)
        return "text/csv; charset=utf-8", buf.getvalue()
    return "application/json; charset=utf-8", json.dumps(
        {"entries": entries}, separators=(",", ":")
    )


def _decode_json_body(body: bytes | str) -> tuple[str | None, dict[str, Any]]:
    raw = body if isinstance(body, (bytes, bytearray)) else str(body or "").encode("utf-8")
    if len(raw) > MAX_HOURS_BYTES:
        return "payload_too_large", {}
    if not raw:
        return None, {}
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "bad_json", {}
    if not isinstance(obj, dict):
        return "bad_json", {}
    return None, obj


def handle_hours_request(
    method: str,
    path: str,
    body: bytes | str,
    home: Path,
    *,
    peer_ip: str = "",
    rate: Any = None,
) -> tuple[int, bytes, str | None]:
    """Dispatch hours routes. Returns (status, body, content_type_override).

    content_type_override is set for CSV export; otherwise None (JSON default).
    """
    verb = (method or "").upper()
    route = (path or "").split("?", 1)[0]
    qs = _parse_query(path or "")

    if rate is not None and verb == "POST":
        key = (peer_ip or "unknown").split("%", 1)[0] or "unknown"
        if not rate.allow(f"hours:{key}"):
            code, payload = _json_error(429, "rate_limited")
            return code, payload, None

    # POST create
    if verb == "POST" and route == HOURS_PATH:
        err, payload = _decode_json_body(body)
        if err == "payload_too_large":
            code, b = _json_error(413, err)
            return code, b, None
        if err:
            code, b = _json_error(400, err)
            return code, b, None
        status, obj = create_entry(home, payload)
        code, b = _json_ok(status, obj)
        return code, b, None

    m = _ACTION_RE.match(route)
    if verb == "POST" and m:
        eid, action = m.group(1), m.group(2)
        err, payload = _decode_json_body(body)
        if err == "payload_too_large":
            code, b = _json_error(413, err)
            return code, b, None
        if err:
            code, b = _json_error(400, err)
            return code, b, None
        if action == "heartbeat":
            status, obj = heartbeat_entry(home, eid, payload)
        elif action == "close":
            status, obj = close_entry(home, eid, payload)
        else:
            status, obj = withdraw_entry(home, eid, payload)
        code, b = _json_ok(status, obj) if "error" not in obj or status < 400 else _json_ok(status, obj)
        return code, b, None

    if verb in ("GET", "HEAD") and route == HOURS_PATH:
        day_from = _parse_day(qs.get("from", "")) if qs.get("from") else None
        day_to = _parse_day(qs.get("to", "")) if qs.get("to") else None
        if qs.get("from") and day_from is None:
            code, b = _json_error(400, "bad_from")
            return code, b, None
        if qs.get("to") and day_to is None:
            code, b = _json_error(400, "bad_to")
            return code, b, None
        user = qs.get("user", "")
        if not user:
            code, b = _json_error(400, "user_required")
            return code, b, None
        entries = filter_entries(
            list_entries(home),
            user=user,
            agent=qs.get("agent", ""),
            customer=qs.get("customer", ""),
            project=qs.get("project", ""),
            ticket=qs.get("ticket", ""),
            status=qs.get("status", ""),
            day_from=day_from,
            day_to=day_to,
        )
        code, b = _json_ok(200, {"entries": entries})
        return code, b, None

    if verb in ("GET", "HEAD") and route == HOURS_PATH + "/summary":
        user = qs.get("user", "")
        if not user:
            code, b = _json_error(400, "user_required")
            return code, b, None
        if qs.get("date"):
            d = _parse_day(qs["date"])
            if d is None:
                code, b = _json_error(400, "bad_date")
                return code, b, None
            day_from = day_to = d
        else:
            day_from = _parse_day(qs.get("from", "")) if qs.get("from") else None
            day_to = _parse_day(qs.get("to", "")) if qs.get("to") else None
            if qs.get("from") and day_from is None:
                code, b = _json_error(400, "bad_from")
                return code, b, None
            if qs.get("to") and day_to is None:
                code, b = _json_error(400, "bad_to")
                return code, b, None
        summary = build_summary(
            list_entries(home), user=user, day_from=day_from, day_to=day_to
        )
        code, b = _json_ok(200, summary)
        return code, b, None

    if verb in ("GET", "HEAD") and route == HOURS_PATH + "/export":
        user = qs.get("user", "")
        if not user:
            code, b = _json_error(400, "user_required")
            return code, b, None
        day_from = _parse_day(qs.get("from", "")) if qs.get("from") else None
        day_to = _parse_day(qs.get("to", "")) if qs.get("to") else None
        if qs.get("from") and day_from is None:
            code, b = _json_error(400, "bad_from")
            return code, b, None
        if qs.get("to") and day_to is None:
            code, b = _json_error(400, "bad_to")
            return code, b, None
        fmt = qs.get("format", "json") or "json"
        if fmt not in ("json", "csv"):
            code, b = _json_error(400, "bad_format")
            return code, b, None
        entries = filter_entries(
            list_entries(home),
            user=user,
            agent=qs.get("agent", ""),
            customer=qs.get("customer", ""),
            project=qs.get("project", ""),
            ticket=qs.get("ticket", ""),
            status=qs.get("status", ""),
            day_from=day_from,
            day_to=day_to,
        )
        ctype, text = export_entries(entries, fmt=fmt)
        return 200, text.encode("utf-8"), ctype

    code, b = _json_error(404, "not_found")
    return code, b, None
