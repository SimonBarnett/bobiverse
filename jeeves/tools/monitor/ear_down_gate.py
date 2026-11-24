#!/usr/bin/env python3
"""FR #9503: verification gate before closing ear-down / bob-ear-dead FRs.

Do not Closes / DONE-close marchhare-class ear-down issues until ALL of:
1. Local (or reported) bob-ear / irc_agent child is alive
2. Digest ``machines.<id>.online == true`` with fresh ``lastSeen``
3. ``!startworker`` ACK on that shop (operator / shop evidence; optional in
   automated monitor path — pass ``startworker_acked=True`` when verified)

Product tips that only ship monitor/heal code must use **Refs** ``#N``, not
``Closes``, until this gate passes. Living pattern matches jeeves exe FR #1993.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

# Align with ircbob_ear DEFAULT_MAX_AGE_SEC.
DEFAULT_MAX_AGE_SEC = 900

_EAR_DOWN_TITLE_RE = re.compile(
    r"(?i)\b("
    r"bob-ear\s+dead|ear-down|ircbob\s+running\s+without|"
    r"running\s+without\s+(?:bob-ear|ear\s+child)|"
    r"online_zero_workers.*ear|ear\s+offline|enospc.*bob-ear"
    r")\b"
)
_EAR_DOWN_BODY_RE = re.compile(
    r"(?i)("
    r"bob-ear\.exe|irc_agent\.py|running without bob-ear|"
    r"ircbob.*without.*child|online_zero_workers|"
    r"!startworker.*ssleoferror|ear-offline"
    r")"
)


def is_ear_down_issue(title: str | None, body: str | None = None) -> bool:
    """True when the issue is an ear-down / bob-ear-dead class FR."""
    t = str(title or "")
    b = str(body or "")
    if _EAR_DOWN_TITLE_RE.search(t):
        return True
    if _EAR_DOWN_TITLE_RE.search(b[:800]):
        return True
    # Body-only: require a strong ear signal (avoid matching unrelated ENOSPC).
    if "bob-ear" in b.lower() and _EAR_DOWN_BODY_RE.search(b):
        return True
    return False


def closes_allowed_for_ear_down(
    title: str | None,
    body: str | None = None,
    *,
    gate_ok: bool,
) -> bool:
    """Ear-down issues may use Closes only when ``gate_ok`` is True."""
    if not is_ear_down_issue(title, body):
        return True
    return bool(gate_ok)


def _parse_iso_age_s(raw: object, now: float) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1_000_000_000_000:
            ts = ts / 1000.0
        if ts > 1_000_000_000:
            return now - ts
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return now - parsed.timestamp()


def digest_machine_online(
    ent: dict | None,
    *,
    now: float,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
) -> tuple[bool, str]:
    """Return (ok, reason) for digest online + fresh lastSeen."""
    if not isinstance(ent, dict):
        return False, "missing machine entry"
    if not ent.get("online"):
        return False, f"online={ent.get('online')!r}"
    status = str(ent.get("status") or "").strip().lower()
    if status in ("i am offline", "offline"):
        return False, f"status={ent.get('status')!r}"
    age = _parse_iso_age_s(ent.get("lastSeen") or ent.get("last_seen"), now)
    if age is None:
        return False, "lastSeen missing"
    if age > max_age_sec:
        return False, f"lastSeen stale age_sec={int(age)} max={int(max_age_sec)}"
    return True, "online+fresh"


def ear_down_gate(
    *,
    ear_child_alive: bool | None,
    machine_ent: dict | None,
    now: float,
    max_age_sec: float = DEFAULT_MAX_AGE_SEC,
    startworker_acked: bool | None = None,
) -> dict[str, Any]:
    """Evaluate the FR #9503 gate.

    ``startworker_acked``:
      - None: not checked (monitor auto path; digest+child still required)
      - True/False: operator/shop evidence included in ok
    """
    reasons: list[str] = []
    child_ok = ear_child_alive is True
    if not child_ok:
        reasons.append(
            f"bob-ear child not alive (ear_child_alive={ear_child_alive!r})"
        )

    dig_ok, dig_reason = digest_machine_online(
        machine_ent, now=now, max_age_sec=max_age_sec
    )
    if not dig_ok:
        reasons.append(f"digest gate failed: {dig_reason}")

    sw_ok = True
    if startworker_acked is not None:
        sw_ok = bool(startworker_acked)
        if not sw_ok:
            reasons.append("!startworker not ACK'd on that shop")

    ok = child_ok and dig_ok and sw_ok
    return {
        "ok": ok,
        "ear_child_alive": ear_child_alive,
        "digest_ok": dig_ok,
        "digest_reason": dig_reason,
        "startworker_acked": startworker_acked,
        "reasons": reasons,
        "fr": 9503,
    }
