# FR #8754 evidence: skip FR offer when Depends-on backlog still open

**Issue:** https://github.com/SimonBarnett/bobiverse/issues/8754

## Accept

1. FR with open Depends-on backlog is not offered.
2. After depends close (leave the queue), the row becomes offerable.

## How measured

1. `fr_depends_on_tokens` reads `Depends-on:` from the issue body and from the linked local `bob/docs/feature-request-*.md` vision pack.
2. `row_fr_depends_blocked_reason` blocks when a Depends-on `BOB-N` or `#N` still appears as an open FR in unaccepted/accepted.
3. `offer_focus_top` / `offer_top` / `!assign` skip or refuse without dropping the row.
4. Tests: `jeeves/tests/test_fr8754_depends_on_skip.py` (BOB-40 vs open BOB-33).

## Distinct from #8741

Park-only / human-dispatch gate is separate. This gate applies to **dispatched** rows with open Depends-on.
