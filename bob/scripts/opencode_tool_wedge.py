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


def signatures_in_text(text: str) -> list[str]:
    """Tool calls visible in one OpenCode run transcript."""
    import re

    found: list[str] = []
    for match in re.finditer(r'Skill\s+"([^"]+)"', text or ""):
        found.append(tool_signature("Skill", {"path": match.group(1)}))
    for match in re.finditer(r"skill-dag_([A-Za-z0-9_]+)", text or ""):
        found.append(tool_signature(match.group(0), {}))
    return found


def observe_output(text: str, *, retries_left: int) -> dict[str, Any]:
    """Decide from one run's output. Idempotent: the whole transcript is re-read."""
    import re

    sigs = signatures_in_text(text)
    if len(sigs) >= WEDGE_IDENTICAL_LIMIT and len(set(sigs[-WEDGE_IDENTICAL_LIMIT:])) == 1:
        return {
            "wedge": True,
            "action": "report-and-giveup",
            "signature": sigs[-1],
            "loop": False,
            "report": True,
        }
    closed = bool(re.search(r"connection closed|MCP error\s*-32000", text or "", re.I))
    if not closed:
        return {"wedge": False, "action": "continue", "loop": False, "report": False}
    decision = after_skill_dag_drop(retries_left=retries_left, skill_loaded=False)
    decision["wedge"] = False
    decision["signature"] = "skill-dag connection closed"
    return decision


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


def main(argv: list[str] | None = None) -> int:
    """`peek <transcript> <retries>` prints one JSON decision. Used by the seat wrapper."""
    import os
    import sys
    from pathlib import Path

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2 or args[0] != "peek":
        return 2
    text = Path(args[1]).read_text(encoding="utf-8", errors="replace")
    retries = int(args[2]) if len(args) > 2 else 0
    decision = observe_output(text, retries_left=retries)
    if decision.get("report") and not os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            import crash_report

            crash_report._post_intake(
                "bug: opencode skill-dag wedge",
                "OpenCode run hit a skill-dag drop or identical tool calls. "
                "The seat gives up and keeps the clicked kind.\n",
                repo="SimonBarnett/bobiverse",
                sig="opencode-skill-wedge",
                exe="bob-worker",
            )
        except Exception:
            pass
    sys.stdout.write(json.dumps(decision) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
