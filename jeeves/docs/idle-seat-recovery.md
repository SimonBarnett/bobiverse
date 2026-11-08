# Idle-seat eligibility recovery (FR #6256)

Deterministic Jeeves recovery when an idle, fueled seat cannot take queued work
because of a **restart-remediable** exclusion, and a fresh same-machine session
would be eligible under existing review policy.

## When it fires

Chair stall scan calls `gitclaim.heal_mrb_reviewer_deadlock`. For
`kind=author_only` (every idle seat is exact-seat author/implementer of every
waiting MRB):

1. Rows are flagged `author_only_deadlock` (FR #5889). Author/implementer
   provenance is **never** erased.
2. FR #6256 may then issue **one** shop-only `!recycleseat <nick> <machine>`
   via `enqueue_recycleseat_shop_only` when all of the following hold:

| Gate | Skip reason token |
|------|-------------------|
| Seat busy / accepted / offered / `working_on` | `recycle_skipped:busy` |
| Seat marked out-of-fuel | `recycle_skipped:out_of_fuel` |
| OpenCode (hostile MRB/UAT skip, FR #6134) | `recycle_skipped:opencode_hostile` |
| Every waiting MRB is CodeRabbit-held only | `recycle_skipped:coderabbit_only` |
| No fresh **per-seat** activity (machine `lastSeen` alone is insufficient) | `recycle_skipped:stale_worker` |
| Recycleseat pending / ACK wait / cooldown (FR #5889) | existing `recycle_skipped:*` |
| Per-machine attempt cap (`IDLE_SEAT_RECOVERY_MAX_ATTEMPTS`, default 3 / 24h) | `recycle_skipped:attempt_cap` |

Fresh worker evidence: `last_activity` / activity file / `worker_list[].updated`
within `WORKER_STATE_FRESH_S` (default 600s). Digest machine heartbeat is not
enough.

## What it does not do

- Does not recycle merely because a seat is idle with no actionable work.
- Does not recycle when another live seat is already an eligible reviewer.
- Does not bypass CodeRabbit holds, focus/ignore, pins, queue locks, or
  `needs_human`.
- Does not start intentionally stopped seats, open key dialogs, or call
  provider quota APIs.
- Does not restart ear, tray, Jeeves, or unrelated machines.
- Does not invent ACK/DONE/`!bored` or forge accepted state. The replacement
  joins its shop and emits its own `!bored`; offers follow the normal path.

## Control handoff

Jeeves decides and enqueues `PRIVMSG #<machine> :!recycleseat <nick> <machine>`.
The machine-side tray/ear performs stop/start of that worker tree only (existing
`recycleseat` controller). Chair-local recycleseat JSON alone never reaches a
remote tray (FR #5220 / #5756).

## Operator surfaces

Stall-heal log lines:

- `mrb-reviewer-deadlock author_only flagged=N (no recycle; needs non-author seat)`
  still appears when flagging; recovery lines are separate:
- `idle-recovery recycleseat=<nick> id=<rid>` on send
- `idle-recovery recycle_skipped:<reason> seat=<nick>` when blocked

Durable state: chair-home `idle-seat-recovery.json` (per-machine attempts /
last nick / signature / result). Shared recycleseat pending + 900s IRC cooldown
prevent duplicate stops across ticks, reconnects, and chair restarts.

## Disable / recognize

- Exhausted attempt cap or cooldown leaves the row flagged; file/ops can add a
  non-author seat or clear give-ups as today.
- To suppress recovery without disabling author_only flags: keep seats without
  fresh worker activity from looking "idle+current", or leave CodeRabbit hold
  stamps in place when that is the real blocker.
- Success looks like: stop verified on the machine, new nick JOINs, normal
  offer, real worker ACK. Process start or heartbeat alone is not queue recovery.
