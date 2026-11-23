# FR #8682 / BOB-38 evidence

Agents > Jeeves loads skills from the skill-dag MCP rooted on `J:\.grok\skills` (J: mapped to Ergo `ai\jeeves`).

- Tray dry-run / log: `jeeves-mcp path=J:\.grok\skills` before start (CS + PS).
- Child env: `BOB_JEEVES_MCP_ROOT=J:\.grok\skills` so `skill_dag_vision_roots` prepends that `--root`.
- Config helper: `bob/scripts/jeeves_j_mcp.py` builds an MCP document whose `--root` is the J: path (not install-worker skills alone).

`python -m pytest -q bob/tests/test_fr8682_jeeves_j_mcp.py`
