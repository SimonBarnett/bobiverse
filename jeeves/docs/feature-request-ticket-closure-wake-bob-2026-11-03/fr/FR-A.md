# FR-A — Deterministic ticket-closure monitor check

## Goal
Add a token-free Jeeves monitor check that reports newly closed issues/PRs on watched/focused repos.

## Deliverables
- `jeeves/tools/monitor/ticket_closure.py` using `_common.run_check`
- `jeeves/scripts/Test-JeevesMonitorTicketClosure.ps1`
- Fixture tests under `jeeves/tests/`

## Testable
- Synthetic close in fixture → exit 1, JSON `closed[]` non-empty
- No new closes → exit 0
- Exit 2 on tool/IO error
- Module does not write `queue.json` or emit `!assign`
