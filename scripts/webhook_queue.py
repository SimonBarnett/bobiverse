"""Durable webhook envelope queue for report/git/intake/jira.

When a handler is offline or processing fails, persist the authenticated POST
envelope under digest home ``webhook-queue/`` and drain on resume. Idempotent
by envelope ``id`` (pending or already-done → no duplicate).
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Callable

WEBHOOK_KINDS = frozenset({"report", "git", "intake", "jira"})
_ID_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def queue_root(home: Path) -> Path:
    p = Path(home) / "webhook-queue"
    p.mkdir(parents=True, exist_ok=True)
    (p / "pending").mkdir(parents=True, exist_ok=True)
    (p / "done").mkdir(parents=True, exist_ok=True)
    return p


def _safe_id(envelope_id: str) -> str:
    eid = str(envelope_id or "").strip()
    if not eid or not _ID_SAFE.fullmatch(eid):
        raise ValueError("bad_envelope_id")
    return eid


def _pending_path(home: Path, envelope_id: str) -> Path:
    return queue_root(home) / "pending" / f"{envelope_id}.json"


def _done_path(home: Path, envelope_id: str) -> Path:
    return queue_root(home) / "done" / f"{envelope_id}.json"


def load_envelope(home: Path, envelope_id: str) -> dict[str, Any] | None:
    eid = _safe_id(envelope_id)
    for path in (_pending_path(home, eid), _done_path(home, eid)):
        if not path.is_file():
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def enqueue(
    home: Path,
    *,
    kind: str,
    payload: dict[str, Any],
    envelope_id: str | None = None,
    headers: dict[str, str] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an envelope. Idempotent: same id already pending/done → return existing.

    Returns the envelope dict (``duplicate=True`` when an earlier copy was reused).
    """
    k = str(kind or "").strip().lower()
    if k not in WEBHOOK_KINDS:
        raise ValueError("bad_kind")
    if not isinstance(payload, dict):
        raise ValueError("bad_payload")
    eid = str(envelope_id or "").strip() or f"wh_{uuid.uuid4().hex[:16]}"
    eid = _safe_id(eid)

    existing = load_envelope(home, eid)
    if existing is not None:
        out = dict(existing)
        out["duplicate"] = True
        return out

    safe_headers: dict[str, str] = {}
    for hk, hv in (headers or {}).items():
        name = str(hk)
        # Never persist shared secrets in the durable queue.
        if name.lower() in ("x-bob-secret", "x-bob-intake-key", "authorization"):
            continue
        safe_headers[name] = str(hv)[:256]

    env: dict[str, Any] = {
        "id": eid,
        "kind": k,
        "payload": payload,
        "headers": safe_headers,
        "meta": dict(meta or {}),
        "enqueued_at": _utc(),
        "state": "pending",
    }
    path = _pending_path(home, eid)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    env["duplicate"] = False
    return env


def mark_done(home: Path, envelope_id: str, *, result: dict[str, Any] | None = None) -> bool:
    """Move pending → done. Returns True if marked (or already done)."""
    eid = _safe_id(envelope_id)
    done = _done_path(home, eid)
    pending = _pending_path(home, eid)
    if done.is_file() and not pending.is_file():
        return True
    if not pending.is_file():
        return False
    try:
        env = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        env = {"id": eid, "state": "pending"}
    if not isinstance(env, dict):
        env = {"id": eid}
    env["state"] = "done"
    env["done_at"] = _utc()
    if result is not None:
        env["result"] = result
    tmp = done.with_suffix(".tmp")
    tmp.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(done)
    pending.unlink(missing_ok=True)
    return True


def list_pending(home: Path, kind: str | None = None) -> list[dict[str, Any]]:
    """Return pending envelopes sorted by filename (stable / chronological-ish)."""
    root = queue_root(home) / "pending"
    want = str(kind or "").strip().lower() or None
    if want is not None and want not in WEBHOOK_KINDS:
        raise ValueError("bad_kind")
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            env = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(env, dict):
            continue
        if want is not None and str(env.get("kind") or "").lower() != want:
            continue
        out.append(env)
    return out


Handler = Callable[[dict[str, Any]], Any]


def process_pending(
    home: Path,
    handlers: dict[str, Handler],
    *,
    kind: str | None = None,
    limit: int = 20,
) -> list[str]:
    """Drain pending envelopes. ``handlers[kind](envelope)``; success → mark_done.

    Handler may return any truthy/None result stored under ``result``. Raising
    leaves the envelope pending. Returns list of completed envelope ids.
    """
    done_ids: list[str] = []
    for env in list_pending(home, kind=kind)[: max(0, int(limit))]:
        eid = str(env.get("id") or "")
        k = str(env.get("kind") or "").lower()
        handler = handlers.get(k)
        if not handler or not eid:
            continue
        try:
            result = handler(env)
        except Exception:
            continue
        mark_done(home, eid, result={"ok": True, "value": result})
        done_ids.append(eid)
    return done_ids


def process_one(
    home: Path,
    envelope_id: str,
    handler: Handler,
) -> bool:
    """Process a single pending envelope by id. False if missing or handler raises."""
    eid = _safe_id(envelope_id)
    pending = _pending_path(home, eid)
    if not pending.is_file():
        return False
    try:
        env = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(env, dict):
        return False
    try:
        result = handler(env)
    except Exception:
        return False
    return mark_done(home, eid, result={"ok": True, "value": result})
