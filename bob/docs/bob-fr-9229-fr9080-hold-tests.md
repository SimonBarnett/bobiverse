# FR #9229: fr9080 hold-label tests vs issues-only hold

## Problem
After FR #9082 (`hold`/`on-hold` issues-only), `pr_hold_reason` no longer treats PR `hold` as a hold. Four `test_fr9080_requeue_preserves_hold_labels` cases still stamped `hold` on PR snapshots and expected `skipped`, so build-jeeves went red on main.

## Fix
Update those tests to use `do-not-merge` (still in `HOLD_MRB_LABELS`). Add a pin that a stale PR `hold` alone does not skip requeue. Linked-issue `hold` remains covered by existing dirty-FIX tests.

## Non-goals
Do not put `hold` back into `HOLD_MRB_LABELS`.