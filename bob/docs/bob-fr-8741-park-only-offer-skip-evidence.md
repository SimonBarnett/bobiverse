# FR #8741 evidence: chair skips park-only anti-omnibus FRs until human dispatch

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8741

## Accept

1. Park-only anti-omnibus FRs are not offered as FR jobs.
2. After a human dispatch stamp, they become offerable.

## How measured

1. `fr_park_only_reason` / `row_fr_park_only_reason` in `common/scripts/gitclaim.py` match park-only / do-not-bob-job cues and clear on `(dispatched)` body or `dispatched` / `human-dispatch` / `bob-dispatched` labels.
2. `_append_unaccepted` skips and drops park-only FRs (same pattern as FR #4009 hold).
3. `offer_focus_top` / `offer_top` / queue heal use `row_fr_skip_offer_reason` (hold or park-only).
4. Tests: `jeeves/tests/test_fr8741_park_only_skip.py`.

## Fail-when

Park-only FRs (e.g. #8675) keep being offered as FR jobs before dispatch.
