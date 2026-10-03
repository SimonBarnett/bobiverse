<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-dispatcher-skip-fix-leftover-fail-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: dispatcher must not FIX leftover FAIL when PR already MERGED

**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/228
**Sister (worker leftover close):** https://github.com/SimonBarnett/agentic_build/issues/227
**Repo:** https://github.com/SimonBarnett/agentic_build
**Date:** 2026-09-23
**Raised by:** MRB of #227 / SHA `52837e5` (hole the harvest made visible)

## Problem

#227 harvests the worker playbook into `bob-hostile-mrb`: if `gh pr merge`
fails and you open FAIL, then the same PR is already MERGED, close that
leftover FAIL with the merged PR URL and do not start FIX.

The actor that starts FIX is the dispatcher (`bob-job-loop` /
`tools/Bob-BuildLoop.ps1` `wait_mrb`): any `MRB FAIL` title → `start_fix`.
A leftover FAIL posted then closed still races the driver into a FIX
worker against a MERGED PR (AgentMonitor #22 class).

## LOCKED

1. When `wait_mrb` sees `MRB FAIL` and `gh pr view` on that loop PR is
   already MERGED, do **not** `start_fix`.
2. Close that leftover FAIL with the merged PR URL. Do not spawn FIX.
3. If the FR is CLOSED or has a PASS-nits merge comment, treat DONE and
   pull main. Do not relaunch a build.
4. Home: `bob-job-loop` + `Bob-BuildLoop.ps1`. Worker leftover close
   stays `bob-hostile-mrb` (#227). Do not duplicate the worker MUST.
5. No UAT stamp. No `password=` / `XAI_API_KEY=` assignments.

## Gap vs current tree

`Bob-BuildLoop.ps1` `wait_mrb` on `$verdict -eq 'FAIL'` always
`start_fix`. `cursor-mrb-dev` still says every FAIL spawns a FIX worker.
`bob-job-loop` already treats PASS-nits merge-in-progress + MERGED as
DONE; it does not gate leftover FAIL.

## Acceptance

- A1: Leftover FAIL + same PR MERGED → no FIX worker.
- A2: Leftover FAIL closes with the merged PR URL.
- A3: Real FAIL (PR still open, acceptance red) still starts FIX.
- A4: Test-Pack off-DEV covers A1/A3. No live GitHub.

## Non-goals

- Re-implementing #227 worker leftover close.
- Closing unrelated stale FAIL boards.
- Ready-for-human-UAT stamp (Bob chair only).
