<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-harvest-bob-job-dispatcher-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: harvest bob-job dispatcher playbook

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/107
**Raised by:** harvest (fleet Bob-job runs on agentic_build / agentic_irc / open-tts)
**UAT + hostile MRB owner:** Bob
**Related:** `docs/feature-request-mrb-loop-automation-2026-09-20.md` (issues #9 / #31), skill `bob-job-loop`, `docs/skill-harvest-log.md`,
https://github.com/SimonBarnett/agentic_build/issues/118
(`docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md`) — PASS-nits
merge-then-close and bar updates live there, not in this harvest scope.

Parked after the harvest issue existed with no `docs/feature-request-*.md`. Spec was pointed at PR #106. This markdown is the intake doc.

## Gap vs current tree

`bob-job-loop` / `Start-BobBuildLoop.ps1` already drive PR → MRB → FIX. Fleet runs showed the dispatcher playbook was still tribal:

1. **GH_TOKEN.** Interactive `git credential fill` fails in a Grok session. Need `git credential-manager get` first, wrapped so stdout stays `DONE` / `FAILED` only.
2. **LogPath collision.** Two loops sharing one log interleave and look dead. Default must include repo + issue; callers pass a unique `-LogPath`.
3. **Wrong PR.** Many open PRs. `wait_pr` must pin `-Sha` / `-Pr` when a PR already exists, and title-match `#<issue>` plus `#<priorMrbIssue>` (FIX titles often name the FAIL board, not the FR). Build / FIX goals must require that title so a worker PR is visible.
4. **gh JSON unzip.** Windows PowerShell `ConvertFrom-Json` can collapse a `gh --json` array into one object with array-valued properties. Reconstruct must keep issue `body` so Required-fixes parse still works (issues #9 / #31).
5. **`$PID`.** Assigning `$pid` overwrites PowerShell's automatic process id and breaks the driver's own bookkeeping.
6. **cursor-agent status.** Stderr / non-zero status must not abort the handoff; treat as not-logged-in / missing agent.
7. **Log lock.** `Add-Content` on a locked log must not kill the loop.

## Ask

1. Add `tools/run-bob-build-loop.ps1`: set GH token from credential-manager, then fill; call `Start-BobBuildLoop.ps1`; stdout `DONE` / `FAILED` only. No secret literals in git.
2. Document isolated worktree per FR and unique `-LogPath` in `bob-job-loop`. Default log name includes repo + issue.
3. `Select-BobBuildLoopPr` accepts `#<issue>` and `#<priorMrbIssue>`. `New-BobBuildGoal` / `New-BobFixGoal` require the PR title to contain that marker. Existing open PR: pin `-Sha` / `-Pr` and start at MRB.
4. `ConvertFrom-BobGhJsonList` reconstructs unzipped lists without dropping issue `body` (or other fields Required-fixes / selectors need).
5. Do not assign PowerShell `$PID`. cursor-agent status stderr is non-fatal. `Write-BobBuildLoopLog` falls back if `Add-Content` is locked.
6. Off-DEV Test-Pack cases for (3) and (4) and parse of the wrapper. No live GitHub in tests.
7. Worker still cannot emit `PASS-UAT`. Driver does not stamp UAT. Bob chairs that.

## Acceptance

1. `tools/run-bob-build-loop.ps1` exists, parses, and prefers credential-manager over interactive fill. No secret values committed.
2. Default and documented `LogPath` include repo + issue. Skill prefers `C:\ai\<repo>-loop<fr>` worktrees.
3. Title match finds a FIX PR named `Fix issue #<priorMrbIssue>` and a first PR named with `#<issue>`. A PR with neither marker is not selected while other open PRs exist. Goals tell the worker to put `#<issue>` or `#<priorMrbIssue>` in the PR title.
4. Unzipped issue JSON still yields a non-empty `body`; `Get-BobMrbRequiredFixes` returns the Required fixes section.
5. `Invoke-LoopStartMrb` (and the rest of the driver) does not overwrite `$PID`.
6. cursor-agent `status` stderr does not throw out of `Start-BobCursor`.
7. Locked `Add-Content` does not throw out of `Write-BobBuildLoopLog`.
8. Test-Pack green off-DEV with cases for AC3 and AC4. No live `gh` / live bridge in those cases.
9. No `PASS-UAT` from worker or driver.

## Non-goals

- Stamping UAT.
- Implementing other open FRs (#9 leftover, #89, #91, #11, …).
- Any MRB PDF.
