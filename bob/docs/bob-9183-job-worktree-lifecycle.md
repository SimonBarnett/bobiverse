# Job worktree prune + disk-low guard (FR #9183)

## Problem
Job worktrees stayed on disk after DONE/GIVEUP/NACK. Soft-cap Clear kept the finished job's own tree as `-KeepPath`, so machines filled until every offer failed with `worktree-create-failed:disk` (flamingo ~90 NACKs).

## Fix
- **After DONE/GIVEUP/NACK:** `remove_finished_job_worktree` runs `git worktree remove --force` then `prune` for that job's path (all seat kinds). Locked trees (e.g. `.pytest_cache`) queue for the next idle retry.
- **Idle:** BoredEmitter calls `idle_worktree_sweep_fn` on idle/start/done/free/turn - drains the locked queue and Clear soft-cap (`MaxExtraJobTrees=0`). Never removes install roots, `_hotpatch_*`, or the seat's current `BOB_JOB_WORKTREE`.
- **Free-space guard:** before worktree create, if free GiB on the destination volume is below `BOB_JOB_WORKTREE_MIN_FREE_GB` (default **5**), sweep once; if still low, NACK `worktree-create-failed:disk-low` and file **one** bobiverse intake per machine per UTC day.

## Ops
- Override floor: `BOB_JOB_WORKTREE_MIN_FREE_GB`
- Idle age hint (future sweeps): `BOB_JOB_WORKTREE_IDLE_MAX_AGE_H` (default 24)
