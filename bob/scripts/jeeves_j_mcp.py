"""FR #8682 / BOB-38: Agents > Jeeves loads skills from the J: skill-dag MCP root."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# J: is mapped to Ergo ai\jeeves; skills live under .grok/skills on that drive.
JEEVES_MCP_SKILLS_ROOT = r"J:\.grok\skills"
ENV_ROOT = "BOB_JEEVES_MCP_ROOT"


def mcp_skills_root(env: dict[str, str] | None = None) -> str:
    """Return the J: MCP skills path (env override for tests)."""
    e = env if env is not None else {}
    # Prefer explicit env when present (seat child), else the J: default.
    import os

    merged = {**os.environ, **e}
    raw = (merged.get(ENV_ROOT) or "").strip()
    return raw if raw else JEEVES_MCP_SKILLS_ROOT


def dry_run_line(env: dict[str, str] | None = None) -> str:
    return "jeeves-mcp path=" + mcp_skills_root(env)


def mcp_config_document(skills_root: str | None = None, *, script: str = "skill_dag_mcp.py") -> dict[str, Any]:
    """Minimal skill-dag MCP config whose --root is under J: (or override)."""
    root = skills_root if skills_root is not None else JEEVES_MCP_SKILLS_ROOT
    return {
        "mcpServers": {
            "skill-dag": {
                "command": "python",
                "args": [script, "--root", root],
            }
        }
    }


def main() -> int:
    print(dry_run_line())
    print(json.dumps(mcp_config_document(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
