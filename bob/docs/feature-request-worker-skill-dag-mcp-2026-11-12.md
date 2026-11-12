# Feature request: worker skill DAG MCP

Repo: `SimonBarnett/bobiverse`. Shape: service.

Vision: `bob/docs/vision-worker-skill-dag-mcp-2026-11-12.md`
Spec: `bob/docs/functional-spec-worker-skill-dag-mcp.md`
Mocks: `bob/docs/mocks/skill-dag/`
FR mirrors: `bob/docs/fr/worker-skill-dag/`

## Ask

Worker skills stay updated by mandatory harvest. Expose them as a DAG through a local MCP. The worker can use a large library. Which skills load depends on the job. The worker does not load the whole library into context.

## Gap against GitHub main

`main` `a5197856` `bob/scripts/bob_worker.py`:

- `worker_prompt` (line 1731) says `FIRST read the skills in {worker_dir}\.grok\skills`.
- `rules_text` (line 1925) says `Read the skills in {folder}\.grok\skills` before doing anything.

No skill-dag MCP is on that tree. Tray mocks stay in `bob/mocks/`.

## Success

See vision Success S1-S8. S7 mechanism stays UNKNOWN until a process-local lever is proven. Do not edit the user `[skills]` table to pass S7.

## Implementation issues (Refs, not a closing keyword)

- #6860 FR-001 skill index builder
- #6861 FR-002 `depends_on` edges on the worker core skills
- #6862 FR-003 local stdio MCP
- #6863 FR-004 worker launch contract
- #6864 FR-005 process-local catalog bound
- #6865 FR-006 Cursor seat wire
- #6866 FR-007 assigned job-worktree skill root

## Follow-up (Refs, not a closing keyword)

- #6901 FR-008 resolve scores skill descriptions. Stays open.
- #6918 job worktree after assign. Completed by #6919. Not reopened.

## Anti-omnibus

One GitHub issue per small FR. This docs PR parks mirrors only. Implementation issues stay open. The follow-up mirror uses the same rule.
