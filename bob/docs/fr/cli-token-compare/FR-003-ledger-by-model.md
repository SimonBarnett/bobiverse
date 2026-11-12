# FR-003 Ledger comparison by model

GitHub: #6783. Stays open. Docs park Refs this issue.

## Goal

`job_costs.by_model` groups measured ledger rows by model so two CLIs can be compared without mixing unknown jobs into the sums.

## Deliverables

- `job_cost_ledger` rollup adds `by_model`.
- Each bucket has `model`, `measured_jobs`, `tokens_in`, `tokens_out`, `tokens_cached`.
- Rows with `tokens_unknown` increment `unknown_jobs` and add nothing to the token sums.
- `digest_section` includes the rollup. No prompts, no secrets.

## Testable

`pytest` loads two measured Grok rows, one measured Cursor row, and one unknown row. The rollup has two model buckets, sums match the measured rows, and `unknown_jobs` is 1.

## Out of scope

Drawing the graph, changing the OpenCode reader, and dollar cost.
