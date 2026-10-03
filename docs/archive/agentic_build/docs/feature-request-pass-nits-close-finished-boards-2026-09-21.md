<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: PASS-nits MUST close finished FR, prior FAIL, and PASS boards

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/118
**Raised by:** hostile MRB of SHA `0b621f0cf3bc583e50124d85d9608fddac9b53c1` (PR #106 / issue #107)
**UAT + hostile MRB owner:** Bob
**Related:** `docs/feature-request-mrb-loop-automation-2026-09-20.md` (issues #9 / #31),
`docs/feature-request-harvest-bob-job-dispatcher-2026-09-21.md` (issue #107),
`docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md`,
skills `bob-hostile-mrb`, `bob-job-loop`, `bob-build-loop`

Parked because SHA `0b621f0` changed the PASS-nits bar and added
`Close-BobBuildLoopFinished` with no intake. That change is a **non-goal** of
#107 and of the loop FR (#9 / #31). Do not implement on the #107 FIX job.

## Gap vs current tree

`bob-hostile-mrb` / `bob-job-loop` already require the MRB worker to **merge**
on PASS-nits. They do **not** require closing the finished feature-request
issue, prior FAIL boards, or the PASS board. Those closes were explicit
non-goals:

- `docs/feature-request-mrb-loop-automation-2026-09-20.md`: "Auto-merging or
  auto-closing the feature-request issue."
- `docs/build-and-test-plan-mrb-loop-automation-2026-09-20.md`: same.
- `docs/feature-request-harvest-bob-job-dispatcher-2026-09-21.md`: "Changing
  FAIL / PASS-nits bars (`bob-hostile-mrb`)."

Evidence the hole is real: issue #107 already had PASS-nits
https://github.com/SimonBarnett/agentic_build/issues/115 which merged
https://github.com/SimonBarnett/agentic_build/pull/114 and still left #107,
prior FAIL #110 / #113, and PASS board #115 **open**.

SHA `0b621f0` on leftover PR #106 implemented a driver closer that:

1. Rewrites the PASS-nits bar in four skills (forbidden on #107).
2. Calls `gh pr merge` then `gh issue close` for `State.issue`,
   `State.priorMrbIssue` (one FAIL only), and `Pass.issue`.
3. Skips when `gh.exe` is missing; swallows merge/close failures
   (`2>$null`, `Continue`); still prints `DONE`.
4. Comments "PR merged" even when merge was skipped or failed.
5. Ships **zero** Test-Pack cases. Official pack on that SHA: 61/0, none
   name `Close-BobBuildLoopFinished`.
6. Sits on PR #106 beside unrelated #91 / #100 tray commits.

This request is the home for the close ritual. Reverses the loop/harvest
non-goals above. Do not land the `0b621f0` SHA as-is.

## Ask

1. After PASS-nits **merge succeeds**, close: the feature-request issue, **every**
   prior FAIL MRB board for that FR (not only `priorMrbIssue`), and this
   PASS-nits issue. Each close comment links the merged PR.
2. Worker does it (`bob-hostile-mrb`). Driver fallback
   (`Close-BobBuildLoopFinished` or replacement) does it if the worker forgot.
3. Fail closed: missing `gh`, failed merge, or failed close is **not** `DONE`.
   Do not close issues if the PR is still open.
4. Comment text must not claim "merged" unless the PR is merged.
5. Off-DEV Test-Pack: close/merge **payload** (issue list + comment +
   merge-if-open). `-Once -TestWorld` must not call live `gh`. No live bridge.
6. Update the loop FR + plan + #107 intake so auto-close is no longer a
   non-goal. Point at this issue.
7. Worker still cannot emit `PASS-UAT`. Driver does not stamp UAT. Bob chairs
   that.

## Acceptance

1. PASS-nits merge of the worker PR is still required. Nits do not block merge.
2. After a successful merge, FR + all prior FAIL boards for that FR + the PASS
   board are closed, each with a comment that names the merged PR URL.
3. First-try PASS (no FAIL boards) closes FR + PASS only.
4. Failed merge leaves all three open. Missing `gh.exe` does not print `DONE`.
5. Test-Pack green off-DEV with cases for (2)(3)(4). No live GitHub.
6. Loop FR #9 / #31 and harvest FR #107 docs no longer list auto-close / bar
   change as a non-goal; they point here.
7. No `PASS-UAT` from worker or driver.

## Non-goals

- Implementing leftover #107 harvest work (already merged via PR #114).
- Implementing #91 / #89 / #79 / #54 / #11 / #12 / #15.
- Closing unfinished FRs or FAIL boards that are still the live board.
- Stamping UAT.
- Any MRB PDF.

## LOCKED

- FAIL still does not merge. Leave the FAIL board open until a later PASS
  closes it. Dispatcher still starts the FIX worker.
- Only Bob stamps ready for human UAT.
- No `password=` / `XAI_API_KEY=` assignments in git.
