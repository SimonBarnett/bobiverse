# FR-006 Cursor worker seat wire

GitHub: #6865. Stays open. Docs park Refs this issue.

## Goal

The Cursor worker seat uses the same skill-dag MCP and the same per-job resolve rule.

## Deliverables

- Record the Cursor MCP config path the seat actually reads.
- Write that file from `bob_worker.py` for cursor launches only.
- Record whether Cursor has a per-workspace switch that drops the skill catalog. Use it only if it is process-local.

## Testable

- Cursor `LaunchSpec` files include the MCP entry and the resolve sentence.
- User Cursor config outside the seat cwd is unchanged.

## Out of scope

Grok S7. Shipping the wire before the Cursor path is measured.
