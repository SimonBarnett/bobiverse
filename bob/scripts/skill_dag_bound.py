"""FR #6864: process-local skill catalog bound for the worker prompt.

Measured levers that must NOT be used (they mutate user Grok config or are dropped):
- writing ``~/.grok/config.toml`` ``[skills]``
- ``GROK_CONFIG`` overlay for ``[skills]`` or ``[mcp_servers]`` (allowlist drops those tables)

Lever that works: never interpolate the skill-dag index into ``worker_prompt`` /
``--rules``. The captured prompt names only the core stub; the seat env carries
``BOB_SKILL_DAG_BOUND=skill-dag-core`` (process-local). User ``config.toml`` is
not opened.
"""
from __future__ import annotations

CORE_STUB_ID = "skill-dag-core"
CORE_STUB_LINE = (
    "Process-local skill catalog is the core stub only (skill-dag-core). "
    "Do not list other skill-dag index nodes in this prompt; resolve per job."
)


def catalog_prompt_bound(index_nodes: list[dict] | None) -> str:
    """Return the prompt fragment for an index of any size (S7: 100+ nodes)."""
    del index_nodes
    return CORE_STUB_LINE


def apply_bound_env(env: dict | None) -> dict:
    out = dict(env or {})
    out["BOB_SKILL_DAG_BOUND"] = CORE_STUB_ID
    out.pop("GROK_CONFIG", None)
    return out
