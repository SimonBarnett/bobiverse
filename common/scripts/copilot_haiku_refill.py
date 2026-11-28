"""FR #9846 / #9884: Haiku CCA refill helpers.

FR #9846: ``SKIP_FAILED_LOOP`` (>= ``min_fails`` failed CCA tasks per FR in
``window_hours``) must not combine with soft-exhausted digest fuel to leave zero
tip-allowlist slots.

FR #9884: when public digest Copilot fuel is soft/hard exhausted, refill must
emit ``NO_FUEL`` and perform zero CCA POSTs (do not burn fail-loop budget).

Rules:
1. Infra soft fails (``missing_conclusion`` / conclusion-unavailable) do not count
   toward the fail-loop budget (ties #9782).
2. When every currently open eligible tip-allowlist FR would be skipped by the
   fail-loop set, clear those tip-allowlist ids from the skip set (bypass) so at
   least one CCA POST remains possible.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

FR_IN_PROMPT = re.compile(r"FR\s*#(\d+)", re.I)

REFILL_NO_FUEL = "NO_FUEL"

_DIGEST_EXHAUST_STATES = frozenset({"exhausted", "quota_exhausted", "failed"})


def digest_blocks_cca_refill(copilot: Mapping[str, Any] | None) -> str | None:
    """FR #9884: block Haiku refill when digest Copilot fuel cannot spend.

    Returns ``REFILL_NO_FUEL`` when soft/hard digest exhaust or pool rules deny
    dispatch; otherwise ``None`` (refill may continue to inflight/fail-loop logic).
    """
    if not isinstance(copilot, Mapping):
        return REFILL_NO_FUEL
    state = str(copilot.get("state") or "").strip().lower()
    if state in _DIGEST_EXHAUST_STATES:
        return REFILL_NO_FUEL
    if copilot.get("exhausted") or copilot.get("tasks_exhausted"):
        return REFILL_NO_FUEL
    import copilot_dispatch as cd

    if not cd.allowance_from_pool(dict(copilot)):
        return REFILL_NO_FUEL
    return None

# Session / task error text that is infra soft-fail (FR #9782), not a real agent fail.
_INFRA_MARKERS = (
    "missing_conclusion",
    "conclusion is not available",
    "conclusion_not_available",
)


def issue_number_from_prompt(prompt: str | None) -> int | None:
    m = FR_IN_PROMPT.search(str(prompt or ""))
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def is_infra_soft_failure(task_or_session: Mapping[str, Any] | None) -> bool:
    """True when a failed CCA task/session is infra soft-fail (do not burn fail-loop)."""
    if not isinstance(task_or_session, Mapping):
        return False
    blobs: list[str] = []
    err = task_or_session.get("error")
    if isinstance(err, Mapping):
        blobs.append(str(err.get("code") or ""))
        blobs.append(str(err.get("message") or ""))
    elif err is not None:
        blobs.append(str(err))
    for key in ("last_infra_error", "message", "status_reason", "failure_reason"):
        if task_or_session.get(key):
            blobs.append(str(task_or_session.get(key)))
    sessions = task_or_session.get("sessions")
    if isinstance(sessions, Sequence):
        for sess in sessions:
            if not isinstance(sess, Mapping):
                continue
            serr = sess.get("error")
            if isinstance(serr, Mapping):
                blobs.append(str(serr.get("code") or ""))
                blobs.append(str(serr.get("message") or ""))
            elif serr is not None:
                blobs.append(str(serr))
            for key in ("message", "status_reason", "failure_reason"):
                if sess.get(key):
                    blobs.append(str(sess.get(key)))
    text = " ".join(blobs).lower()
    return any(m in text for m in _INFRA_MARKERS)


def _parse_created_at(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def failed_loop_issue_ids(
    tasks: Iterable[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    window_hours: float = 3.0,
    min_fails: int = 2,
    exclude_infra: bool = True,
) -> set[int]:
    """Return FR issue numbers that hit the fail-loop skip threshold.

    Each task mapping may include ``state``, ``created_at``, and either a top-level
    ``prompt`` or ``sessions[0].prompt`` (CCA agents API shape). Infra soft fails
    are omitted when ``exclude_infra`` is true (FR #9782 / #9846).
    """
    now_dt = now or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)
    cutoff = now_dt - timedelta(hours=float(window_hours))
    counts: dict[int, int] = {}
    for task in tasks:
        if not isinstance(task, Mapping):
            continue
        if str(task.get("state") or "").lower() != "failed":
            continue
        created = _parse_created_at(task.get("created_at"))
        if created is None or created < cutoff:
            continue
        if exclude_infra and is_infra_soft_failure(task):
            continue
        prompt = task.get("prompt")
        if not prompt:
            sessions = task.get("sessions")
            if isinstance(sessions, Sequence) and sessions:
                sess0 = sessions[0]
                if isinstance(sess0, Mapping):
                    prompt = sess0.get("prompt")
        issue = issue_number_from_prompt(str(prompt) if prompt is not None else None)
        if issue is None:
            continue
        counts[issue] = counts.get(issue, 0) + 1
    return {n for n, c in counts.items() if c >= int(min_fails)}


def apply_tip_allowlist_fail_loop_bypass(
    failed_skip: Iterable[int],
    tip_allowlist: Sequence[int],
    open_eligible_tip_frs: Sequence[int],
) -> tuple[set[int], str | None]:
    """Clear tip-allowlist ids from ``failed_skip`` when they would starve all tip slots.

    ``open_eligible_tip_frs`` is the allowlist subset that is still OPEN and eligible
    for CCA (not tip-PR-green, not digest/held, not lesson-only). When that set is
    non-empty and every member is in ``failed_skip``, remove allowlist members from
    the skip set and return reason ``tip_allowlist_bypass``.

    When the allowlist has no open eligible FRs left, leave ``failed_skip`` unchanged
    (reason ``tip_allowlist_exhausted``).
    """
    skip = {int(x) for x in failed_skip}
    allow = [int(x) for x in tip_allowlist]
    if not allow or not skip:
        return skip, None
    open_tips = [int(x) for x in open_eligible_tip_frs]
    if not open_tips:
        blocked = [n for n in allow if n in skip]
        if blocked:
            return skip, "tip_allowlist_exhausted"
        return skip, None
    still_free = [n for n in open_tips if n not in skip]
    if still_free:
        return skip, None
    # Every open tip FR is fail-loop blocked -> bypass tip-allowlist members.
    cleared = {n for n in skip if n not in set(allow)}
    return cleared, "tip_allowlist_bypass"


def resolve_failed_skip_for_refill(
    tasks: Iterable[Mapping[str, Any]],
    *,
    tip_allowlist: Sequence[int],
    open_eligible_tip_frs: Sequence[int],
    now: datetime | None = None,
    window_hours: float = 3.0,
    min_fails: int = 2,
    exclude_infra: bool = True,
) -> tuple[set[int], str | None]:
    """Full FR #9846 path: fail-loop ids then tip-allowlist bypass."""
    raw = failed_loop_issue_ids(
        tasks,
        now=now,
        window_hours=window_hours,
        min_fails=min_fails,
        exclude_infra=exclude_infra,
    )
    return apply_tip_allowlist_fail_loop_bypass(raw, tip_allowlist, open_eligible_tip_frs)
