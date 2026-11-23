# FR #9239: bob-ear MemoryError in outbox_loop

## Problem
Walrus bob-ear `1.0.8` filed `MemoryError` at `take_outbox_records` → `pathlib.read_bytes` while draining `outbox.txt`. A large backlog made the ear load the entire file each tick.

## Fix
- `take_outbox_records` seeks to the drain offset and reads at most `OUTBOX_READ_MAX_BYTES` (default 1 MiB, override `BOB_OUTBOX_READ_MAX_BYTES`).
- Optional `max_bytes=` for callers (CRED-SEAL prefix sweep).
- Soft-return `([], last)` on `MemoryError` with an ERROR log.
- `sweep_cred_seal_prefix` walks `[0, upto)` in chunks.

## Non-goals
No outbox compaction/rotate in this FR. No VERSION bump.
