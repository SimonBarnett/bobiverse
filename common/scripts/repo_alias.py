"""Canonical GitHub repo names plus recognised aliases (FR #7121).

Priority skill-book repo: ``SimonBarnett/priority-mcp`` (was
``SimonBarnett/agentic_fomprep``). One table for Jeeves / intake / queue keys.
"""
from __future__ import annotations

PRIORITY_MCP_CANONICAL = "SimonBarnett/priority-mcp"
PRIORITY_MCP_ALIAS = "SimonBarnett/agentic_fomprep"

# lower owner/name or short name -> canonical owner/name
_REPO_CANON: dict[str, str] = {
    "simonbarnett/priority-mcp": PRIORITY_MCP_CANONICAL,
    "simonbarnett/agentic_fomprep": PRIORITY_MCP_CANONICAL,
    "priority-mcp": PRIORITY_MCP_CANONICAL,
    "agentic_fomprep": PRIORITY_MCP_CANONICAL,
}


def canonicalize_repo(repo: str) -> str:
    """Map a recognised alias to the live GitHub full_name; otherwise return input."""
    raw = str(repo or "").strip().strip("/")
    if not raw:
        return raw
    key = raw.lower()
    if key in _REPO_CANON:
        return _REPO_CANON[key]
    if "/" in key:
        owner, _, name = key.partition("/")
        mapped = _REPO_CANON.get(name)
        if mapped and owner in ("simonbarnett", "simonbarnett"):
            return mapped
    return raw


def repos_equivalent(a: str, b: str) -> bool:
    """True when both names are the same live repo (alias or case)."""
    left, right = canonicalize_repo(a), canonicalize_repo(b)
    if not left or not right:
        return False
    return left.strip().lower() == right.strip().lower()
