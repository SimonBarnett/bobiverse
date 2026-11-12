# FR-003 Local stdio skill-dag MCP

GitHub: #6862. Stays open. Docs park Refs this issue.

## Goal

Serve `resolve`, `get_skill`, and `status` over local stdio with a byte budget and a path allowlist.

## Deliverables

- Stdio MCP process, no listening port.
- `resolve` returns the matched ids plus `depends_on` ancestors, and skipped ids when over budget.
- `get_skill` returns one body only for a path under the configured roots.
- `status` returns index time, node count, and last error.
- No list-all tool.

## Testable

- S2: FR resolve includes job-irc and excludes an unattached UAT fixture (`pytest`).
- S4: a fat body is skipped and the response length stays within the cap.
- A path outside the roots is refused.

## Out of scope

Writing `config.toml`. Changing the launch prompt.
