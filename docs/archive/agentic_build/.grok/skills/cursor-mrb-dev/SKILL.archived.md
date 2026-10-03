<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path .grok/skills/cursor-mrb-dev/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: cursor-mrb-dev
description: >
  Hand off hostile MRB per bob-mrb-worker: Cursor Models while remaining > 0,
  else grok.exe. Workers open PRs. After PASS, review docs and merge exactly
  one docs PR with the original when stale. FAIL → exactly one fix PR then
  merge both (not a FIX-worker chain). Leftover FAIL after another seat already
  merged: close the board, no extra fix. Use when the user says cursor mrb,
  mrb until pass, cursor builder, re-mrb, mrb/dev loop, or /cursor-mrb-dev.
  Launch: start-bob-cursor. Verdicts: bob-hostile-mrb. Standard: bob-mrb-worker.
  Table: bob-build-loop. Bob stamps UAT.
github: https://github.com/SimonBarnett/agentic_build
---

# MRB / one-fix until PASS

Foundation: `harvest-agent-skills` (honesty box) -> report back to
https://github.com/SimonBarnett/agentic_build.

**STANDARD process:** `bob-mrb-worker` (tests-first; PASS docs review then
merge, with exactly one docs PR when stale; FAIL one fix PR then merge both). Transaction pointer: `bob-build-loop`.
Bob does not write the MRB or the code. Hand off, watch GitHub, dispatch
the next row.

## Fuel (no judgment)

Number source: `bob-token-handoff` (live digest `pcent.cursor-models` first). Do not invent it.

`Select-BobGitWorker` / default `-Fuel cursor-models`.

- Cursor Models remaining > 0: Cursor Agent. MRB = Cursor Grok
  (`models.mrbCursor` = `grok-4.6`). PR = Composer (`composer-2.5`).
- Remaining = 0, or cursor-agent not logged in: grok.exe. MRB = `grok-4.6`.
  PR = `build0.1` if listed, else `grok-4.5`.
- Never Other Models. Copilot only with `-AllowCopilot`.

Show remaining: `box-usage` / tray top bar. Catalog mapping:
`Resolve-BobGrokCliModel`.

## Login

`start-bob-cursor`: `cursor-agent status` must be logged in. Never
`~\.grok\bin\agent.exe` (that is grok). If Cursor is not logged in,
`Start-BobMrbHandoff` falls back to grok-build.

## GitHub posting (preflight)

Before `Start-BobMrbHandoff` starts an agent, the **worker box** must post
issues and merge PRs. `Get-BobGhPostingReadiness` probes live auth (not just
env presence): `gh.exe` present, `gh auth status` OK, and `gh repo view`
on the product repo (`SimonBarnett/agentic_build` or `BOB_PRODUCT_REPO`).

### Token contract (unattended fleet boxes)

| Item | Rule |
|---|---|
| Env var | `GH_TOKEN` preferred; `GITHUB_TOKEN` also honored by `gh` |
| Scopes | `issues:write` and `pull_requests:write` on the product repo (classic PAT or fine-grained repo access) |
| Where it lives | **User-level** Windows env or Credential Manager from interactive `gh auth login` — never git, job packets, or prompts |
| Rotation | Regenerate the PAT on GitHub, update the user env (or re-run `gh auth login`), then `Install-BobFleet` / `Get-BobHealth` should show `gh_posting.issue_posting_ready=true` |
| Probe | `Get-BobHealth.gh_posting`, `Get-BobCapacity.machines[].gh_posting`, tray `Get-BobTrayHover.gh_posting` |

Remediation when preflight fails: `winget install GitHub.cli` (or
`Install-BobFleet`), then set `GH_TOKEN` or `gh auth login`. See
`Get-BobGhExe` / `tools/Bob-Gh.ps1`. When `BOB_GH_EXE` is set to a path that
does not exist, `Get-BobGhExe` returns `$null` (it does not fall through to a
system `gh.exe`). Off-DEV Test-Pack points `BOB_GH_EXE` at
`tests/fixtures/Fake-Gh.ps1`.

`Select-BobGitWorker -Kind mrb` skips machines with
`gh_posting.issue_posting_ready=false`. Grok-build fallback still runs on the
**dispatcher** box until the remote worker is verified (issue #11 handoff
checks).

If preflight fails, fix auth first. Do not start the MRB agent.

### Test-Pack-only seams on `Start-BobMrbHandoff.ps1`

`-TestSkipCursor` and `-TestGitWorkerResult` exist only for `tools/Test-Pack.ps1`.
`-TestSkipCursor` requires `-Fuel grok-build` and `-TestGitWorkerResult`. Do not
use them in live MRB dispatch.

Workers post via `tools/Start-BobMrb.ps1` (creates missing `mrb` /
`mrb-pass` / `mrb-fail` labels).

## Loop

Driver: `tools/Start-BobBuildLoop.ps1` / `tools/run-bob-build-loop.ps1`
(skill `bob-job-loop`). Launch it and wait for `DONE`. It starts the PR
worker if needed, hands off MRB to a **new** `-Kind mrb` agent, retries
failed cursor/grok jobs, reads Required fixes on FAIL, back-links boards,
and exits on PASS-nits. On FAIL, FIX stays on this FR. After DONE, start
**one** `bob-job-loop` for the **next** queued FR (receive order;
`bob-job-loop`). Do not retype `Start-BobMrbHandoff` / `Start-BobBuild -Fix`
by hand unless
the driver cannot start. Do not resume the implementer to review their
own PR.
Board state: `Get-BobMrbBoard` in `tools/Bob-BuildLoop.ps1`.

Transaction table: `bob-build-loop`. Bars: `bob-hostile-mrb`. Standard:
`bob-mrb-worker`. Launch primitives: `start-bob-cursor`. Only **Bob**
stamps ready for human UAT.

## Watch

The driver prints `DONE` / `FAILED` only. Watch that, plus the **GitHub
issue and PR**, not the redirected `.log`. Confirm `node.exe --model
grok-4.6` (MRB) or `--model composer-2.5` (PR) when fuel is cursor-models.

## Hard

- No MRB PDFs.
- No `password=` / `XAI_API_KEY=` assignments.
- Do not burn Grok Bot weekly when Cursor Models or grok.exe can take it.
- Do not spawn multiple fix PRs for one FAIL (`bob-mrb-worker`).
