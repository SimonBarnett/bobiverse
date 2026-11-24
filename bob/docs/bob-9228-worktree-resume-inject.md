# FR #9228: OpenCode park worktree create must resume ACK+inject

## Problem
RedQueen OpenCode seat parked `worktree create` for FIX #9125, the tree appeared, but the seat never ACK'd or injected. It stayed `opencode-ready: idle` and kept `!bored`. Resume after ensure either soft-failed (duplicate / re-park) with no log, or ensure hung without a clear worker.log line.

## Fix
- `_worktree_create_then_deliver` logs `worktree ensure ok|nack` and `worktree create resume status=...`
- `deliver(..., resume_after_worktree=True)` clears soft-duplicate, never re-parks; if classify still absent after ensure, NACK `worktree-create-failed:verify`
- Soft resume statuses force `_force_ack_inject_after_worktree` (ACK+inject)
- `maybe_log_stale_worktree_offer` (180s) surfaces parked creates with no ACK in worker.log

## Non-goals
Tray untouched. Operator restarts OC seats when needed.
