<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-mrb-loop-automation-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: MRB loop automation — per-SHA board, back-link, off-DEV coverage

**Date:** 2026-09-20
**Repo:** https://github.com/SimonBarnett/agentic_build
**Raised by:** MRB worker (Cursor Models) while reviewing 6a53bd4 for issue #8
**UAT + hostile MRB owner:** Bob
**Related:** `.grok/skills/cursor-mrb-dev` (landed 6a53bd4), `.grok/skills/bob-hostile-mrb`,
https://github.com/SimonBarnett/agentic_build/issues/118
(`docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md`) — PASS-nits
merge-then-close finished FR / FAIL / PASS boards (driver + worker).

## Gap vs current tree

`cursor-mrb-dev` (landed in 6a53bd4) describes a loop: MRB the SHA → new
`MRB FAIL|PASS-nits: ... <sha>` issue → hand the Required fixes to a Cursor build
worker → re-MRB the new SHA → repeat until PASS-nits. Nothing in the tree drives
that loop. Today it is a human retyping `Start-BobMrbHandoff.ps1` with a new
`-Sha`, and the steps below have no code at all:

1. **Back-link.** `bob-hostile-mrb` says "Comment on the prior FAIL issue with the
   new URL." No tool does this. `Start-BobMrb.ps1` creates an issue and returns;
   it does not know the prior board.
2. **Loop driver.** No `Start-BobMrbLoop` / no state file recording
   `(feature issue, sha, mrb issue, verdict)` per pass, so nothing can answer
   "which SHA is the current board and how many passes has this FR burned".
3. **Fix handoff.** `cursor-mrb-dev` step 3 tells the operator to call
   `tools/Start-BobCursor.ps1 -Kind build -Mrb <issue>` by hand. The MRB issue's
   Required fixes are not read by anything; the goal text is retyped.
4. **Off-DEV coverage.** `tools/Test-Pack.ps1` has no case for the handoff path.
   `BT0 skills` only asserts `SKILL.md` exists and `name:` matches the folder. A
   regression in `Start-BobMrbHandoff.ps1` / `Start-BobCursor.ps1` argument
   plumbing ships green.

## Ask

1. A loop driver `tools/Start-BobBuildLoop.ps1` (skill `bob-job-loop`; board
   reader `Get-BobMrbBoard`) that: starts the PR worker if the FR is parked
   without a tip SHA, waits for the PR, hands off MRB, waits for the new
   `mrb`-labelled issue, and records each pass in a state file under the
   bridge root. The calling agent launches the program and is notified on
   stdout (`DONE` / `FAILED` only) when MRB PASS-nits. No live GitHub in tests.
2. Auto back-link: when a new MRB issue is created for a FR that already has an
   open `mrb-fail` board, comment the new URL on the old board. When a FIX PR
   opens, comment that PR URL on the FAIL board.
3. Fix handoff reads the Required fixes section out of the MRB issue body rather
   than requiring the operator to paste a goal.
4. Retry failed cursor-agent / grok.exe **jobs** (process died, enqueue refused,
   `completion.status` not ok, no PR / no MRB issue). Do not treat an MRB FAIL
   verdict as a job crash: that is a FIX worker. Fuel is re-read each start;
   cursor start failure falls back to grok-build.
5. Off-DEV Test-Pack cases (Fake-Grok / fixture, no live `gh`, no live
   `cursor-agent`) for: handoff argument plumbing, `-Kind` propagation from a job
   packet, fallback to `grok-build` when Cursor is not logged in, the
   per-SHA title contract, Required-fixes parse, back-link payload, retry, and
   PASS-nits terminal.

## Acceptance

1. Test-Pack green off-DEV with new cases; none of them touch live GitHub, live
   `%USERPROFILE%\.grok\bob-bridge`, or a live agent.
2. Given a fixture prior FAIL issue, the driver produces a back-link comment
   payload (asserted off-DEV, not posted).
3. Loop state file names the feature issue, each SHA, and each verdict.
4. `cursor-mrb-dev` / `bob-hostile-mrb` / `bob-build-loop` point at the driver
   instead of describing manual repetition. Skill `bob-job-loop` is the launch.
5. Worker still cannot emit `PASS-UAT`. The driver does not stamp UAT. Bob stamps
   UAT.
6. Failed cursor/grok jobs retry up to `maxJobRetries` (default 3 attempts per
   phase). Exhaustion prints `FAILED` and exits non-zero.
7. PASS-nits prints `DONE: MRB PASS-nits ...` and exits 0. No progress lines on
   stdout (monitor-safe).

## Non-goals

- Any MRB PDF.
- Letting the loop driver stamp ready for human UAT.
