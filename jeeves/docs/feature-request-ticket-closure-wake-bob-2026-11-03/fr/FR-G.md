# FR-G — Wait registry (Phase-2 optional)

## Goal
Let Bob register `waiting_on: [owner/repo#N]` so wakes can narrow later.

## Deliverables
- Registry file or digest field Bob/seat can update
- ticket_closure filters to registry when non-empty; Phase-1 behavior when empty

## Testable
- Empty registry → Phase-1 all focused closes still wake
- Non-empty → only matching ids wake
