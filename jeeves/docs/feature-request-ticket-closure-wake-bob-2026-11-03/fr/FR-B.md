# FR-B — De-dupe cursor for closures

## Goal
Each closure key wakes or findings at most once.

## Deliverables
- State file e.g. `monitor-ticket-closure.json` under digest/ops home
- Keys include owner/repo#N + event identity (closed_at / delivery id)
- ticket_closure skips already-seen keys

## Testable
- Same close processed twice → second run exit 0 / empty new closes
- New distinct close → exit 1 again
