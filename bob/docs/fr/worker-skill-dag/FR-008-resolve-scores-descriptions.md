# FR-008 Resolve scores skill descriptions

GitHub: #6901. Stays open. Docs park Refs this issue.

## Goal

`resolve` scores the job line against skill descriptions, then adds `depends_on` ancestors inside the byte budget. A first-token map of FR, MRB, UAT, and FIX is not scoring.

## Deliverables

- `resolve` scores the job line against each node's one-line description.
- The winning node plus `depends_on` ancestors are returned inside the byte budget. The seed stays when it fits.
- FR, MRB, UAT, and FIX lines still select the job skills.
- No list-all tool. No listen port.

## Testable

- A fixture line that shares words with one skill description, and does not start with FR, MRB, UAT, or FIX, returns that skill id.
- A line that matches nothing returns an empty matched list.
- `resolve("FR owner/repo#1 do the work")` still includes `bobiverse-bob-job-fr` when that node is in the index and under budget.

## Evidence

On `origin/main` `531ceb22`, `bob/scripts/skill_dag_mcp.py`:

- `_seed_id` (line 220) takes the first whitespace token. If it is in `JOB_SEEDS` (FR, MRB, UAT, FIX) it returns that skill id. Otherwise it returns the raw string.
- `resolve` (line 245) closes `depends_on` from that id and returns each node's description. It does not use the description to choose the seed.

#6890 (folded descriptions, job-line seeds, seed-first budget) is closed completed. #6918 (job worktree after assign) is closed completed by #6919. Neither slice is this one.
