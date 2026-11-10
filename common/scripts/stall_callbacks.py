"""FR #6439: Jeeves stall webhook callbacks (reuse ticket-closure wake transport).

Posts HTTPS callbacks to ``JEEVES_TICKET_CLOSURE_WAKE_URL`` (same secret/auth as
close notices) when the chair detects stalls. Debounces one callback per
``(event, subject)`` until clear or 60 minutes. Failed POSTs stay in pending
with backoff. No secrets in payloads or persisted state.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

STATE_NAME = "stall-callbacks.json"
DEBOUNCE_S = 60 * 60.0
WAKE_BACKOFF_S = 60.0
WAKE_BACKOFF_MAX_S = 900.0
HEARTBEAT_HOUR_UTC = 6  # daily heartbeat around 06:00 UTC
IDLE_WITH_WORK_S = 10 * 60.0

# FR event names (payload ``event`` field). Close notices use ``close``.
EVENT_CLOSE = "close"
EVENT_IDLE_WITH_WORK = "idle_with_work"
EVENT_OFFER_TIMEOUT = "offer_timeout"
EVENT_GIVEUP = "giveup"
EVENT_SELF_REVIEW_DEADLOCK = "self_review_deadlock"
EVENT_SEAT_DOWN = "seat_down"
EVENT_RESYNC_FAILED = "resync_failed"
EVENT_RATE_LIMITED = "rate_limited"
EVENT_CHAIR_DEGRADED = "chair_degraded"
EVENT_HEARTBEAT = "heartbeat"

ALL_EVENTS = frozenset(
    {
        EVENT_CLOSE,
        EVENT_IDLE_WITH_WORK,
        EVENT_OFFER_TIMEOUT,
        EVENT_GIVEUP,
        EVENT_SELF_REVIEW_DEADLOCK,
        EVENT_SEAT_DOWN,
        EVENT_RESYNC_FAILED,
        EVENT_RATE_LIMITED,
        EVENT_CHAIR_DEGRADED,
        EVENT_HEARTBEAT,
    }
)

# stall_detectors id -> FR event name
_DETECTOR_EVENT = {
    "self-review-deadlock": EVENT_SELF_REVIEW_DEADLOCK,
    "all-gave-up": EVENT_GIVEUP,
    "ack-stale": EVENT_OFFER_TIMEOUT,
    "bored-latency": EVENT_SEAT_DOWN,
    "stale-digest": EVENT_CHAIR_DEGRADED,
    "resync-fail": EVENT_RESYNC_FAILED,
    "idle-with-work": EVENT_IDLE_WITH_WORK,
}

_SECRET_RX = re.compile(
    r"(?i)(token|bearer|password|secret|api[_-]?key|authorization)\s*[:=]\s*\S+"
)
_WAKE_HTTP_POST: Callable[..., Any] | None = None
_CLOCK: Callable[[], float] = time.time


def _wake_url() -> str:
    raw = (
        os.environ.get("JEEVES_TICKET_CLOSURE_WAKE_URL")
        or os.environ.get("JEEVES_BOB_WAKE_URL")
        or ""
    ).strip()
    if not raw:
        return ""
    if (urllib.parse.urlparse(raw).scheme or "").lower() != "https":
        return ""
    return raw


def _wake_secret() -> str:
    return (
        os.environ.get("JEEVES_TICKET_CLOSURE_WAKE_SECRET")
        or os.environ.get("JEEVES_BOB_WAKE_SECRET")
        or ""
    ).strip()


def wake_configured() -> bool:
    return bool(_wake_url())


def event_enabled(event: str) -> bool:
    """Per-event switch (default on). ``JEEVES_STALL_CALLBACK_<EVENT>=0`` disables."""
    ev = str(event or "").strip().lower()
    if not ev:
        return False
    env = f"JEEVES_STALL_CALLBACK_{ev.upper()}"
    raw = (os.environ.get(env) or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def redact_payload_value(text: str) -> str:
    return _SECRET_RX.sub(r"\1=***", str(text or ""))[:240]


def build_callback_payload(
    *,
    event: str,
    repo: str = "",
    number: Any = "",
    seat: str = "",
    machine: str = "",
    since: Any = None,
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Minimal stall/close callback body. Never includes secrets or log dumps."""
    ev = str(event or "").strip().lower() or EVENT_CLOSE
    num: Any = ""
    if number is not None and str(number).strip() != "":
        try:
            num = int(number)
        except (TypeError, ValueError):
            s = str(number).strip().lstrip("#")
            num = int(s) if s.isdigit() else s
    out: dict[str, Any] = {
        "event": ev,
        "repo": str(repo or "").strip(),
        "number": num,
        "seat": str(seat or "").strip(),
        "machine": str(machine or "").strip(),
        "reason": redact_payload_value(reason),
    }
    if since is not None:
        out["since"] = since
    if extra:
        for k, v in extra.items():
            key = str(k)
            if key.lower() in ("token", "secret", "password", "authorization", "api_key"):
                continue
            if key in out:
                continue
            out[key] = v
    return out


def assert_no_secrets(payload: dict[str, Any]) -> None:
    """Raise AssertionError if payload JSON looks like it carries secrets (tests)."""
    raw = json.dumps(payload, sort_keys=True)
    # Allow intentional redaction markers from redact_payload_value.
    scrubbed = re.sub(
        r"(?i)(token|bearer|password|secret|api[_-]?key|authorization)\s*[:=]\s*\*\*\*",
        "",
        raw,
    )
    if _SECRET_RX.search(scrubbed):
        raise AssertionError("secret-shaped field in stall callback payload")
    for bad in ("Bearer ", "password=", "api_key=", "WAKE_SECRET"):
        if bad.lower() in scrubbed.lower():
            raise AssertionError(f"forbidden token {bad!r} in payload")


def state_path(home: Path) -> Path:
    return Path(home) / STATE_NAME


def load_state(home: Path) -> dict[str, Any]:
    p = state_path(home)
    if not p.is_file():
        return {"debounced": {}, "pending": {}, "cleared": {}, "last_heartbeat_day": ""}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {"debounced": {}, "pending": {}}
    except Exception:
        return {"debounced": {}, "pending": {}}


def save_state(home: Path, state: dict[str, Any]) -> None:
    # Never persist secrets.
    blob = {
        "debounced": state.get("debounced") if isinstance(state.get("debounced"), dict) else {},
        "pending": state.get("pending") if isinstance(state.get("pending"), dict) else {},
        "cleared": state.get("cleared") if isinstance(state.get("cleared"), dict) else {},
        "last_heartbeat_day": str(state.get("last_heartbeat_day") or ""),
    }
    raw = json.dumps(blob, indent=2) + "\n"
    secret = _wake_secret()
    if secret and secret in raw:
        raw = raw.replace(secret, "***")
    state_path(home).write_text(raw, encoding="utf-8")


def debounce_key(event: str, subject: str) -> str:
    return f"{str(event or '').strip().lower()}|{str(subject or '').strip().lower()}"


def _default_http_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "bobiverse-jeeves-stall-callbacks",
            **headers,
        },
        method="POST",
    )
    opener = urllib.request.build_opener(
        urllib.request.HTTPHandler(), urllib.request.HTTPSHandler()
    )
    with opener.open(req, timeout=30) as resp:
        status = int(getattr(resp, "status", 200) or 200)
        if status >= 400:
            raise ConnectionError(f"wake HTTP {status}")
        return {"ok": True, "status": status}


def post_callback(payload: dict[str, Any]) -> dict[str, Any]:
    url = _wake_url()
    if not url:
        return {"ok": False, "error": "no_wake_url"}
    headers: dict[str, str] = {}
    secret = _wake_secret()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Bob-Wake-Secret"] = secret
    poster = _WAKE_HTTP_POST or _default_http_post
    try:
        poster(url, payload, headers)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": type(e).__name__}
    return {"ok": True}


def _subject_from_finding(finding: dict[str, Any]) -> str:
    key = str(finding.get("key") or "").strip()
    if key:
        return key
    ev = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
    for k in ("row", "machine", "nick"):
        v = str((ev or {}).get(k) or "").strip()
        if v:
            return v
    return str(finding.get("id") or "unknown")


def finding_to_event(finding: dict[str, Any]) -> str:
    det = str(finding.get("id") or "").strip().lower()
    if det == "resync-fail":
        evd = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
        status = evd.get("status")
        try:
            if int(status) == 429:
                return EVENT_RATE_LIMITED
        except (TypeError, ValueError):
            if str(status).lower() in ("429", "rate_limited", "rate-limited"):
                return EVENT_RATE_LIMITED
    return _DETECTOR_EVENT.get(det, "")


def finding_to_payload(finding: dict[str, Any], *, now: float) -> dict[str, Any]:
    event = finding_to_event(finding)
    evd = finding.get("evidence") if isinstance(finding.get("evidence"), dict) else {}
    repo = ""
    number: Any = ""
    row = str((evd or {}).get("row") or finding.get("key") or "")
    if "#" in row:
        repo, _, num = row.partition("#")
        number = num
    waiting = (evd or {}).get("waiting")
    if (not repo) and isinstance(waiting, list) and waiting:
        first = str(waiting[0] or "")
        if "#" in first:
            repo, _, num = first.partition("#")
            number = num
    reason = str(finding.get("title") or finding.get("id") or event)
    return build_callback_payload(
        event=event,
        repo=repo,
        number=number,
        seat=str((evd or {}).get("nick") or ""),
        machine=str((evd or {}).get("machine") or ""),
        since=now,
        reason=reason,
    )


def _debounce_ok(state: dict[str, Any], key: str, now: float) -> bool:
    deb = state.get("debounced") if isinstance(state.get("debounced"), dict) else {}
    prev = deb.get(key)
    try:
        last = float(prev) if prev is not None else 0.0
    except (TypeError, ValueError):
        last = 0.0
    if last and (now - last) < DEBOUNCE_S:
        return False
    return True


def _mark_debounced(state: dict[str, Any], key: str, now: float) -> None:
    deb = state.setdefault("debounced", {})
    if not isinstance(deb, dict):
        deb = {}
        state["debounced"] = deb
    deb[key] = float(now)


def clear_debounce(home: Path, event: str, subject: str) -> None:
    """Clear debounce when a stall condition resolves (optional)."""
    state = load_state(home)
    key = debounce_key(event, subject)
    deb = state.get("debounced") if isinstance(state.get("debounced"), dict) else {}
    if key in deb:
        deb.pop(key, None)
        state["debounced"] = deb
        save_state(home, state)


def enqueue_callback(
    home: Path,
    payload: dict[str, Any],
    *,
    subject: str = "",
    now: float | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Debounce + POST (or pending). No-op when wake URL unset or event disabled."""
    now_f = float(now if now is not None else _CLOCK())
    event = str(payload.get("event") or "").strip().lower()
    if not wake_configured():
        return {"ok": True, "skipped": "no_wake_url"}
    if not event_enabled(event):
        return {"ok": True, "skipped": "event_disabled"}
    subj = subject or str(payload.get("repo") or "") + "#" + str(payload.get("number") or "")
    if not str(subj).strip():
        subj = event
    key = debounce_key(event, subj)
    state = load_state(home)
    if not force and not _debounce_ok(state, key, now_f):
        return {"ok": True, "skipped": "debounced", "key": key}
    result = post_callback(payload)
    if result.get("ok"):
        _mark_debounced(state, key, now_f)
        # Drop matching pending if any.
        pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
        pending.pop(key, None)
        state["pending"] = pending
        save_state(home, state)
        return {"ok": True, "posted": True, "key": key}
    # Persist for retry (no secrets).
    pending = state.setdefault("pending", {})
    if not isinstance(pending, dict):
        pending = {}
        state["pending"] = pending
    item = dict(payload)
    item["_subject"] = subj
    item["_next_try"] = now_f + WAKE_BACKOFF_S
    item["_fails"] = int((pending.get(key) or {}).get("_fails") or 0) + 1
    pending[key] = item
    save_state(home, state)
    return {"ok": False, "pending": True, "key": key, "error": result.get("error")}


def drain_pending(home: Path, *, now: float | None = None) -> dict[str, Any]:
    """Retry failed stall callbacks (same backoff idea as ticket_closure)."""
    now_f = float(now if now is not None else _CLOCK())
    if not wake_configured():
        return {"drained": 0, "remaining": 0}
    state = load_state(home)
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    drained = 0
    for key, item in list(pending.items()):
        if not isinstance(item, dict):
            pending.pop(key, None)
            continue
        try:
            nxt = float(item.get("_next_try") or 0)
        except (TypeError, ValueError):
            nxt = 0.0
        if nxt and now_f < nxt:
            continue
        payload = {
            k: v
            for k, v in item.items()
            if not str(k).startswith("_")
        }
        result = post_callback(payload)
        if result.get("ok"):
            pending.pop(key, None)
            _mark_debounced(state, key, now_f)
            drained += 1
            continue
        fails = int(item.get("_fails") or 1) + 1
        delay = min(WAKE_BACKOFF_MAX_S, WAKE_BACKOFF_S * (2 ** min(fails, 4)))
        item["_fails"] = fails
        item["_next_try"] = now_f + delay
        pending[key] = item
    state["pending"] = pending
    save_state(home, state)
    return {"drained": drained, "remaining": len(pending)}


def emit_findings(
    home: Path,
    findings: list[dict[str, Any]],
    *,
    now: float | None = None,
) -> list[dict[str, Any]]:
    """Map stall_detectors findings to debounced callbacks."""
    now_f = float(now if now is not None else _CLOCK())
    actions: list[dict[str, Any]] = []
    if not wake_configured():
        return [{"skipped": "no_wake_url"}]
    drain_pending(home, now=now_f)
    for finding in findings or []:
        if not isinstance(finding, dict):
            continue
        event = finding_to_event(finding)
        if not event:
            continue
        payload = finding_to_payload(finding, now=now_f)
        subject = _subject_from_finding(finding)
        actions.append(
            enqueue_callback(home, payload, subject=subject, now=now_f)
        )
    return actions


def emit_giveup(
    home: Path,
    *,
    repo: str,
    number: Any,
    seat: str = "",
    machine: str = "",
    reason: str = "",
    now: float | None = None,
) -> dict[str, Any]:
    """Fire when a shop GIVEUP/NACK returns a job (FR #6439 giveup event)."""
    payload = build_callback_payload(
        event=EVENT_GIVEUP,
        repo=repo,
        number=number,
        seat=seat,
        machine=machine,
        since=now if now is not None else _CLOCK(),
        reason=reason or "giveup",
    )
    subject = f"{repo}#{number}:{seat or 'seat'}"
    return enqueue_callback(home, payload, subject=subject, now=now)


def emit_offer_timeout(
    home: Path,
    *,
    repo: str,
    number: Any,
    seat: str = "",
    reason: str = "offer_timeout",
    now: float | None = None,
) -> dict[str, Any]:
    payload = build_callback_payload(
        event=EVENT_OFFER_TIMEOUT,
        repo=repo,
        number=number,
        seat=seat,
        since=now if now is not None else _CLOCK(),
        reason=reason,
    )
    return enqueue_callback(
        home, payload, subject=f"{repo}#{number}:offer", now=now
    )


def maybe_heartbeat(home: Path, *, now: float | None = None) -> dict[str, Any]:
    """Daily heartbeat so the receiver can tell quiet from unreachable."""
    if not wake_configured() or not event_enabled(EVENT_HEARTBEAT):
        return {"ok": True, "skipped": "disabled_or_no_url"}
    now_f = float(now if now is not None else _CLOCK())
    day = time.strftime("%Y-%m-%d", time.gmtime(now_f))
    hour = int(time.strftime("%H", time.gmtime(now_f)))
    state = load_state(home)
    if str(state.get("last_heartbeat_day") or "") == day:
        return {"ok": True, "skipped": "already_today"}
    if hour < HEARTBEAT_HOUR_UTC:
        return {"ok": True, "skipped": "before_hour"}
    payload = build_callback_payload(
        event=EVENT_HEARTBEAT,
        reason="daily heartbeat",
        since=now_f,
    )
    # Heartbeat uses force so debounce does not block the daily fire; day stamp is the gate.
    result = enqueue_callback(
        home, payload, subject="heartbeat", now=now_f, force=True
    )
    if result.get("posted") or result.get("pending"):
        state = load_state(home)
        state["last_heartbeat_day"] = day
        save_state(home, state)
    return result
