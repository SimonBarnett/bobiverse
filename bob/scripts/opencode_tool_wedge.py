"""FR #7705: OpenCode tool-loop and skill-dag drop decisions.

A dropped skill-dag MCP session must reconnect once, then report and GIVEUP.
Three identical tool calls in a row are a wedge. Recovery never changes the
seat kind Si clicked (FR #7692).
"""
from __future__ import annotations

import json
from typing import Any, Callable

WEDGE_IDENTICAL_LIMIT = 3


def tool_signature(name: str, arguments: object = None) -> str:
    try:
        payload = json.dumps(arguments or {}, sort_keys=True, default=str)
    except TypeError:
        payload = str(arguments)
    return f"{name}\n{payload}"


def note_identical_tool_call(
    recent: list[str],
    name: str,
    arguments: object = None,
    *,
    limit: int = WEDGE_IDENTICAL_LIMIT,
) -> dict[str, Any]:
    """Append one call. On `limit` identical signatures, ask for report + GIVEUP."""
    sig = tool_signature(name, arguments)
    recent.append(sig)
    if len(recent) > limit:
        del recent[:-limit]
    tail = recent[-limit:]
    if len(tail) >= limit and len(set(tail)) == 1:
        return {
            "wedge": True,
            "action": "report-and-giveup",
            "signature": sig,
            "loop": False,
        }
    return {"wedge": False, "action": "continue", "signature": sig, "loop": False}


def after_skill_dag_drop(*, retries_left: int, skill_loaded: bool) -> dict[str, Any]:
    """What the seat does when skill-dag stdio closes mid-session.

    Reconnect while retries remain. If the FR job skill is still missing,
    report and GIVEUP. Never return a loop action.
    """
    if skill_loaded:
        return {"action": "continue", "report": False, "loop": False}
    if int(retries_left) > 0:
        return {"action": "reconnect", "report": False, "loop": False}
    return {"action": "giveup", "report": True, "loop": False}


def recovery_keeps_seat_kind(clicked_kind: str) -> str:
    """FR #7692: a restart after this wedge is the same kind Si clicked."""
    return str(clicked_kind or "").strip().lower()


def report_wedge(
    report_fn: Callable[..., Any],
    *,
    reason: str,
    signature: str,
    seat_kind: str,
) -> dict[str, Any]:
    """Hand the wedge to the fleet reporter. Does not change seat kind."""
    body = {
        "reason": reason,
        "signature": signature[:200],
        "seat_kind": recovery_keeps_seat_kind(seat_kind),
        "action": "giveup",
    }
    report_fn(body)
    return body
