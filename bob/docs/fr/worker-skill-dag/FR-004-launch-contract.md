# FR-004 Worker launch contract

GitHub: #6863. Stays open. Docs park Refs this issue.

## Goal

The worker launch tells the agent to resolve per job, and registers the MCP only on the worker cwd.

## Deliverables

- `worker_prompt` and agent `rules_text` in `bob/scripts/bob_worker.py` name `resolve` and `get_skill`.
- They no longer say to read every skill in the folder.
- `[mcp_servers]` for skill-dag is written to the worker cwd `.grok/config.toml` only.

## Testable

- S5: `pytest` on `worker_prompt` and `rules_text`.
- S6: launch fixture leaves the plan cwd and `~/.grok/config.toml` unchanged.

## Out of scope

S7 catalog suppression. Cursor config filename. Global `grok mcp add`.
