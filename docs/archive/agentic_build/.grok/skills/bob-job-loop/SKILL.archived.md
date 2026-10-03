<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-job-loop/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-job-loop
description: >
  Hand off starting a git job and hostile MRB until PASS: run
  Start-BobBuildLoop.ps1 (or tools/run-bob-build-loop.ps1) and get notified
  on DONE. Retries failed cursor/grok jobs. FAIL spawns FIX. After PASS-nits,
  hand remaining open issues (not only feature-request) to new workers.
  Does not stamp UAT. Use when the user says hand off the job, bob job,
  bob job FRs, start and mrb until pass, retry failed cursor/grok jobs,
  run the program and notify on PASS-nits, or /bob-job-loop. Fuel gate:
  bob-token-handoff (live digest first; PR=low, MRB=medium, UAT=high).
  Table: bob-build-loop. Bars: bob-hostile-mrb. Bob listens and assigns only.
---

# Build / MRB until PASS (one program)

Foundation: `harvest-agent-skills` (honesty box) -> report back to
https://github.com/SimonBarnett/agentic_build.

Transaction table: `bob-build-loop`. Fuel and login: `bob-token-handoff`
then `cursor-mrb-dev` / `start-bob-cursor`. Verdicts: `bob-hostile-mrb`.

The dispatcher does not sit in the MRB table. Launch the driver, then
stop. Do not poll `Get-BobBuild`. Do not retype `Start-BobMrbHandoff` or
`Start-BobBuild -Fix` unless the driver cannot start. Bob listens and
assigns only.

## Fuel (do not re-reason)

Before the driver starts a worker, the number comes from the **live digest
webhook** (`bob-token-handoff`, `https://irc.ntsa.uk/bob/v1/report`
`pcent.cursor-models`). Do not invent it. MarchHare has no Cursor login.

- Cursor Models remaining > 0 -> `cursor-models`, else grok.exe (`grok-build`).
- **PR = low** code agent: Composer `composer-2.5`, or `build0.1` if listed, else `grok-4.5`.
- **MRB = medium** code agent: `grok-4.6`. New worker. Never the implementer.
- **UAT = high**: Bob assigns and stamps UAT. This loop does not stamp UAT. Do not spend a high agent to implement or to MRB.
- Never Other Models. Copilot only with `-AllowCopilot`.
- Maximize free/cheap agents when included fuel remains. The driver re-reads fuel at each start; the source of the percent is still the digest.

## Launch (Grok session)

FR + plan already parked (`bob-spec-intake`). Prefer isolated worktree per
FR. Unique `-LogPath` per loop (two loops must not share one log file).

```powershell
# Prefer the wrapper (GH_TOKEN via credential-manager; fill often fails):
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ai\agentic_build\tools\run-bob-build-loop.ps1 `
  -Repo owner/repo -Issue <fr> -Cwd C:\ai\<repo>-i<fr> `
  -Docs docs/feature-request-....md -Plan docs/build-and-test-plan-....md `
  -LogPath $env:USERPROFILE\.grok\long-running-background-tasks\bob-build-loop-owner_repo-<fr>.log
```

Or `tools/start-bob-build-loop-issue.ps1` (same GCM token path). Or call
`Start-BobBuildLoop.ps1` in-process with `$env:GH_TOKEN` already set.

Skip `-Goal` unless the parked issue is not enough. Existing PR: pass
`-Sha <pr-head>` and `-Pr <url>` to start at MRB.

From this Grok session, wrap the launch in `monitor` so a single stdout
line wakes you. Stdout is `DONE` / `FAILED` only.

Board: `$BOB_BRIDGE_HOME\loops\<owner>_<repo>-<issue>.json`
(default `~\.grok\bob-bridge\loops\`).

## FR queue (receive order)

Work **one FR at a time** until MRB **PASS-nits** (`phase=pass` on its loop
board, driver stdout `DONE`). Do **not** start the next FR while the current
one is still building, in MRB, or in FIX.

**Queue order**

1. User-stated sequence wins (e.g. “#70 then #73”).
2. Else: open `feature-request` issues on that repo, **lowest issue number
   first** (proxy for received order when parked in order).
3. Skip issues already `phase=pass`, closed, or superseded.

**While the head of the queue is open:** no second loop on a later FR for the
same repo (no parallel build/MRB on #70 and #73). Chained wrappers must
wait for the prior loop to exit `DONE` before launching the next. An older FR
still in `wait_mrb` / `wait_pr` (e.g. #56) blocks starting a newer FR (#70)
unless the human explicitly reprioritizes and pauses the older board.

After PASS-nits on the current FR, launch **only** the next queued FR (one
`run-bob-build-loop.ps1`, new worktree + log). Missing-features issues parked
by MRB join the **tail** of the queue in issue-number order.

## Dispatcher hard rules

1. One FR, one loop board, one isolated cwd/worktree.
2. Unique `LogPath` / default log name includes repo + issue.
3. `GH_TOKEN`: GCM / `git credential-manager get` first; do not rely on
   interactive `git credential fill` (often fails when `gh` is the helper).
4. Existing open PR for that FR (or its `priorMrbIssue` FAIL board): pin
   `-Sha`/`-Pr` and start at MRB. Do not spawn another build that ignores
   the open PR.
5. Title match accepts `#<issue>` and `#<priorMrbIssue>` (FIX PRs often
   say `Fix issue #21` while the FR is `#2`).
6. Never the implementer for MRB. New job, `-Kind mrb`.
7. On `FAILED: PR worker exited without a PR`: list open PRs; if a matching
   PR exists (or a local branch with the work), push if needed, re-pin the
   board to `idle`/`wait_mrb` with `-Sha`/`-Pr`, and relaunch. Do not burn
   three more blind builds first.
8. **MRB FAIL** follows `bob-mrb-worker`: the MRB seat opens **exactly one**
   fix PR and merges original + fix (not a FIX-worker chain). **Also** pass
   to a new worker when any open actionable issues remain after this FR's
   PASS / Missing features park. Do not stop at one FR DONE while open work
   sits idle. Skip boards already `phase=pass` and superseded issues.
9. **No Bob, still open issues -- find a seat (Simon 2026-09-22):** after
   MRB, if Bob is absent and open actionable issues remain, do not park
   the channel waiting for Bob. Ask `#bobiverse` for a spare to take the
   next issue, or start the next `bob-job-loop` yourself. Harvest into
   skills when this rule is learned (`harvest-agent-skills`).
10. **Check open issues as well as FRs (Simon 2026-09-22):** when bob-job
    looks for work (first launch, after PASS-nits, short-of-work, no-Bob),
    run `gh issue list --state open` on the repo -- **not only**
    `--label feature-request`. Actionable = any open issue that is not a
    pure MRB meta board (`mrb` + `mrb-pass`/`mrb-fail`, titles starting
    `MRB PASS-nits:` / `MRB FAIL:`). Unlabeled or other-label open issues
    are work: park intake via `bob-spec-intake` if needed, then loop.
    Also scan open PRs the same way.
11. **Talk seats own bob jobs (Simon 2026-09-22):** `the bob jobs are
    YOURS`. Idle `{machine}-{pid}` talk seats run `bob-job-loop` on
    unowned open issues. Do not leave the queue to `bob-*` / Watch
    (`marchhare is busy`). Desktop utils are not a substitute for a
    live loop. First claim on IRC + the issue wins; do not second a
    live loop.
12. **If you get a FR, you bob job it (Simon 2026-09-23):** after
    `bob-spec-intake` parks the issue + `/docs`, start `bob-job-loop`
    on that issue. Do not leave a new FR as park-only unless Simon
    said park-only / later.

## On wakeup

- `DONE: MRB PASS-nits ...` -- tell the human the issue, SHA, and PR. Do
  not stamp ready for human UAT. Bob chairs that. Confirm the MRB
  **merged the PR, closed the finished FR / FAIL / PASS issues, and
  pulled the merge onto product main** (Simon 2026-09-22 -- VERY
  important). If merge/close was skipped, run `Close-BobBuildLoopFinished`
  and `git fetch` + fast-forward before anything else. Then list **all
  open issues** on that repo (not only `feature-request`); for each
  actionable issue not already PASS and not superseded, launch a new
  `bob-job-loop` (isolated worktree + unique log) **from the pulled
  main**. Also launch any issues the MRB just parked under Missing
  features.
- `FAILED: ...` -- read the loop log. Fix the reason (auth, cwd, missed PR,
  secrets in the goal), then relaunch. Do not start a second loop on the
  same FR while one is still alive.
- `FAILED: PASS-nits finish: PR still open after gh pr merge` -- race.
  If `gh pr view` is already MERGED and the FR issue is CLOSED (or has
  PASS merge comment), treat as DONE. Do not relaunch a build.
- `FAILED: PASS-nits finish: gh pr merge failed: GraphQL: Merge already
  in progress` -- same race. `gh pr view --json merged` is invalid (no
  such field); that made `Test-BobGhPrIsMerged` always false and skipped
  the close. Re-check `--json state,mergedAt`. If `state` is MERGED,
  close leftover FR / FAIL / PASS boards and pull. Do not relaunch.
- Before the driver dismisses a worker (DONE or last FAILED), remind it
  to harvest repeatable playbooks (`harvest-agent-skills`). Empty harvest:
  no commit.

## What the driver does

1. Start a **build** worker (`-Kind build`) if there is no tip SHA.
2. Wait for a PR. Cursor/grok job crash or no PR: retry (max 3 attempts
   per phase). Cursor start miss falls back to grok-build. Fuel is
   re-read each start.
3. Start a **new** MRB worker (`Start-BobMrbHandoff`, `-Kind mrb`). Never
   the implementer. Seed / rules must include `bob-mrb-worker`.
4. Wait for `MRB FAIL|PASS-nits: ... <sha>`. Job crash without that issue:
   retry the MRB job.
5. FAIL: MRB seat opens **exactly one** fix PR and merges original + fix
   (`bob-mrb-worker`). If `gh pr view` on the loop PR is already MERGED
   (leftover FAIL after a merge race): close that FAIL with the merged PR
   URL; do not open another fix. Comment the fix PR URL on the prior FAIL
   issue when the one fix runs.
6. PASS: the MRB worker already **merged the PR**, **closed** the
   finished FR, prior FAIL boards, and PASS board, and **pulled** the
   completed PR onto product main (see `Close-BobBuildLoopFinished` in
   `tools/Bob-BuildLoop.ps1` if the worker skipped a close). If `gh pr
   view` is MERGED but local main is behind, `git fetch` + fast-forward
   before printing `DONE`. Print `DONE` and exit 0.

Never Other Models. Copilot only with `-AllowCopilot`. No MRB PDF. No
`password=` / `XAI_API_KEY=` assignments. Test-Pack seams: `-Once`
`-TestWorld` only.

## GitHub hygiene (do not troll old boards)

After messy MRB cycles or before picking the next FR, sweep the repo so
open lists show **current** work only:

```powershell
# Issues: PASS boards, superseded FAIL, loop-pass FRs
tools/Close-BobMrbPassedIssues.ps1 -Repo owner/repo

# PRs: duplicate FIX stacks, stale PRs when the FR is already closed
tools/Close-BobSupersededGithub.ps1 -Repo owner/repo -ProtectPrNumbers <active-pr>

# Retro merge when PASS boards exist but gh merge was skipped earlier
tools/Merge-BobMrbPassOpenPrs.ps1 -Repo owner/repo
```

MRB **PASS-nits** must use `Start-BobMrb.ps1 -PrUrl <url>` (merges with
`gh pr merge --merge` before posting). Loop `DONE` also runs
`Close-BobBuildLoopFinished` (merge + close). Protect the PR on an
**active** loop board (`phase` not `pass`/`failed`) via `-ProtectPrNumbers`.
