# FR #9082 evidence — hold is issues-only

## Policy
`hold` / `on-hold` are **issues-only**. Never stamp them on pull requests. Gate work by holding the linked FR/issue (FR #4009) and/or owner `HOLD:` body stamps / `do-not-merge` / `wip` on the PR.

## Changes
- `gitclaim.HOLD_MRB_LABELS` drops `hold`/`on-hold`; adds `strip_issues_only_hold_labels` + `pr_forbidden_hold_labels`
- `intake._filer_create_pr` strips those labels before create
- Monitor `pr_hold_labels` EXIT 1 when an open PR still carries them
- GitHub label `hold` description updated to say issues-only

## Tests
`python -m pytest -q jeeves/tests/test_fr9082_hold_issues_only.py jeeves/tests/test_fr3928_mrb_hold_and_pass_gate.py::test_pr_hold_reason_from_label`
