# FR #8911 evidence

When skill-dag MCP fails the initialize handshake and the bound cwd only has skill-dag-core, the seat runs `python <scripts>/skill_dag_mcp.py --once resolve` then `get_skill` from seat `.cursor/mcp.json`. A working CLI continues the job. Both failing is GIVEUP `skill-dag-mcp-down`. Reading `SKILL.md` from another job worktree is not a fallback.

`python -m pytest -q bob/tests/test_fr8911_skill_dag_handshake_fallback.py`
