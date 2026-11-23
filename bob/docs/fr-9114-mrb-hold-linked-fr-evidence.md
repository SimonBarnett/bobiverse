# FR #9114 evidence: MRB hold uses live linked FR labels

## Problem
Harvest-lesson MRB #8748 GIVEUP on-hold after FR #8677 hold and PR hold labels were removed, still citing a 2026-11-21 HOLD comment.

## Fix
- `mrb_merge_gate.resolve_linked_fr_hold` reads Closes / FR mentions and issue labels.
- When linked FRs are checked and none held, stale PR HOLD comments do not refuse merge.
- Linked FR with `hold` / `on-hold` still refuses (`linked FR hold active`).
- bobiverse-bob-job-mrb + harvest skills document FR #9114.

## Tests
`python -m pytest -q common/tests/test_fr9114_mrb_hold_linked_fr.py`
