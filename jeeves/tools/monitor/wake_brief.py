"""FR #6067: shared wake-message brief for ticket_closure and Wake-GrokBotBob."""
from __future__ import annotations

from typing import Any

CONTINUE_CUE = "Continue waiting work."
_KINDS = frozenset({"issue", "pr"})
_STATES = frozenset({"closed", "merged"})


class WakeBriefError(ValueError):
    """Missing or invalid required brief field."""


def build_wake_brief(item: dict[str, Any]) -> str:
    """Build one actionable wake line. Required: repo, number, kind, state."""
    if not isinstance(item, dict):
        raise WakeBriefError("missing item")
    repo = str(item.get("repo") or "").strip()
    owner, sep, name = repo.partition("/")
    if not sep or not owner or not name or "/" in name:
        raise WakeBriefError("missing repo")
    raw_n = item.get("number")
    if isinstance(raw_n, bool) or isinstance(raw_n, float):
        raise WakeBriefError("missing number")
    try:
        if isinstance(raw_n, int):
            number = raw_n
        else:
            s = str(raw_n or "").strip()
            if not s.isdigit():
                raise ValueError("not digits")
            number = int(s)
    except (TypeError, ValueError):
        number = 0
    if number <= 0:
        raise WakeBriefError("missing number")
    kind = str(item.get("kind") or "").strip().lower()
    if kind not in _KINDS:
        raise WakeBriefError("missing kind")
    state = str(item.get("state") or item.get("event") or "").strip().lower()
    if state not in _STATES:
        raise WakeBriefError("missing state")
    title = str(item.get("title") or "").strip()
    core = f"{state} {kind} {repo}#{number}"
    if title:
        return f"{core} {title} {CONTINUE_CUE}"
    return f"{core} {CONTINUE_CUE}"
