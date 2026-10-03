<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/bob-build-dispatch/SKILL.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: bob-build-dispatch
description: >
  Write a build-and-test plan under /docs and Start-BobBuild on a legion machine.
  Use when the user says start the build agent, dispatch build, build0.1, kick
  the parked spec, pick fuel, or /bob-build-dispatch. Requires docs already
  parked (see bob-spec-intake). Fuel gate is bob-token-handoff (live digest
  first). Job polling is grok-build-fleet. Bob listens and assigns only.
---

# Build plan + dispatch

## 1. Build-and-test plan

Write `docs/build-and-test-plan.md` in the target repo (commit + push) that a build agent can execute without more questions:

- Goals / non-goals
- Phase order with exit criteria
- Suggested tree / commands
- Locked config constants
- Test IDs and CI rules
- Definition of done for the first ticket
- Kickoff prompt block for `Start-BobBuild -Goal`

## 2. Choose machine (or let the picker)

Git tasks: `Start-BobBuild -Task git` with **optional** `-Machine` / `-Fuel`.
Default is `Select-BobGitWorker` (capacity pair, not a nick called cursor).

**Fuel, before Start-BobBuild:** follow `bob-token-handoff`. Do not re-reason it.

1. Read the live digest webhook first (`https://irc.ntsa.uk/bob/v1/report`, `pcent.cursor-models`). Do not invent the percent. MarchHare has no Cursor login.
2. Cursor Models remaining > 0 -> `cursor-models`, else `grok-build`. `-AllowCopilot` adds copilot only after that. Never Other Models.
3. Code agents: **PR = low** (Composer `composer-2.5`, or grok.exe `build0.1` when listed, else `grok-4.5`). **MRB = medium** (`grok-4.6`). **UAT = high** (Bob assigns only; Bob stamps UAT). Maximize free/cheap agents when included fuel remains.
4. Bob listens and assigns only. Bob does not implement and does not write the MRB.

Override remains: `-Machine flamingo -Fuel grok-build` for formprep / MSSQL. `-Fix` re-runs the picker. Transaction: `bob-build-loop`. Handoff: `cursor-mrb-dev`.

Ids: `ionos`, `marchhare`, `dev1`, `flamingo` -- not hostnames. DUMB / 2012
is not a git worker.

Load BobBridge from the local agentic_build clone (`C:\ai\agentic_build`, `D:\ai\agentic_build`, or `C:\src\agentic_build`). Run `Get-BobHealth` / `Get-BobMachines` / `Get-BobCapacity`. Heal a dead watcher via `grok-build-fleet`.

## 3. Start-BobBuild

Point `-Cwd` at the **product** repo checkout on that machine (clone first if needed).

Goal should tell the build agent to read `docs/functional-spec.md` and `docs/build-and-test-plan.md`, implement the first ticket/phases, **open a PR**, and paste the test summary. Never push `main`. Never merge.

Constraints (examples):

- Do not invent APIs or procedure names the spec forbids
- Do not put password= or API key **assignments** in prompts or commits
- PR workers: low tier (Composer `composer-2.5`, or `build0.1` if `grok models` has it, else `grok-4.5`). MRB: medium (`grok-4.6`). Do not use Other Models. Fuel number from `bob-token-handoff` (digest first).
- Keep prior version folders intact on feature work
- Success = PR URL, not a push to main

`ReplyChannel` is usually `Bob`. Profile is usually `generic` (use `formprep` only for Priority Form Prep on DEV).

Prefer instructional wording for secrets ("do not set an API key environment variable"). Never paste `XAI_API_KEY=...` values. Bare name mentions are OK.

## 4. After dispatch

- Tell the human `jobId` + machine.
- Poll `Get-BobBuild` / reply_channel pings (see `grok-build-fleet`).
- On the worker PR, run `bob-job-loop` (`Start-BobBuildLoop.ps1`) so MRB/FIX
  retries until PASS-nits (GitHub issue, not a PDF). Single-SHA handoff:
  `bob-hostile-mrb` / `cursor-mrb-dev`.

## Long jobs

Product builds often exceed a few minutes. Rely on Watch-BobAgents for unning_orphan / inbox_stale / gent_stall. Do not Stop-BobBuild solely because wall time feels long while the worker process is alive. Prefer profiles.generic.timeoutSec >= 7200 on legion boxes.