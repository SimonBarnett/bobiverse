# FR-005 Process-local catalog bound

GitHub: #6864. Stays open. Docs park Refs this issue.

## Goal

Prove a process-local way to keep unrelated skill descriptions out of the worker prompt.

## Deliverables

- A written result: the lever that works, or evidence that none of the measured levers work.
- The worker launch uses that lever only if it leaves `~/.grok/config.toml` unchanged.
- Do not set the user `[skills]` table. Do not use `GROK_CONFIG` for `[skills]` or `[mcp_servers]`.

## Testable

- S7: with an index of at least 100 nodes, the captured worker prompt lists only the core stub.
- If no lever exists, the test stays red and the issue records the commands tried.

## Out of scope

Editing Plan-seat or human Grok sessions. A new Grok release owned outside this repo.
