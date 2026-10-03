<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-mrb-loop-automation-2026-09-20.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: MRB loop driver (start + MRB until PASS-nits)

**Date:** 2026-09-20
**Spec:** `docs/feature-request-mrb-loop-automation-2026-09-20.md`
**Related:** https://github.com/SimonBarnett/agentic_build/issues/118 — PASS-nits
merge-then-close (`docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md`).
**Chair:** Bob

## Goals

A dispatcher agent runs one program and is notified when hostile MRB
PASS-nits. The program starts the PR worker if needed, hands MRB to a
different worker, retries failed cursor/grok jobs, and spawns FIX on
MRB FAIL. It does not stamp UAT.

## Non-goals

- MRB PDFs.
- Live GitHub or live `cursor-agent` in Test-Pack.

## Tree

| Path | Role |
|---|---|
| `tools/Bob-BuildLoop.ps1` | Pure decision + state + Required-fixes parse + back-link payload |
| `tools/Start-BobBuildLoop.ps1` | Runner: observe GitHub/jobs, execute starts, stdout DONE/FAILED |
| `.grok/skills/bob-job-loop/SKILL.md` | Agent launch: run the program, wait for DONE |
| `tools/Test-Pack.ps1` BT0x* | Off-DEV cases with `-Once` / `-TestWorld` |

State file: `$BOB_BRIDGE_HOME/loops/<owner>_<repo>-<issue>.json` (never the
live `%USERPROFILE%\.grok\bob-bridge` in tests).

## Phases

`idle` -> `wait_pr` -> `wait_mrb` -> (`start_fix` -> `wait_pr`) or `pass`.

- Artifact is the law: PR URL for build, `MRB FAIL|PASS-nits: ... <sha>`
  issue for MRB.
- Cursor fleet "handed ok" is not worker success. Watch pid + GitHub.
- Job crash (dead pid, grok `completion.status` not ok, start refused, no
  artifact) -> retry same kind, max 3 attempts. Cursor start miss -> grok-build.
- MRB FAIL -> FIX worker with Required fixes as the goal. Not a job retry.

## Test IDs

| ID | Assert |
|---|---|
| BT0 skills | `bob-job-loop` SKILL.md `name:` matches |
| BT0 parse | new `*.ps1` parse |
| BT0x1 | Required-fixes section extracted from fixture body |
| BT0x2 | back-link payload names new URL + SHA (not posted) |
| BT0x3 | state file round-trip: issue, sha, verdict |
| BT0x4 | wait_pr + dead job + no PR -> `retry_job` |
| BT0x5 | wait_mrb + FAIL title -> `start_fix` goal contains Required fixes |
| BT0x6 | wait_mrb + PASS-nits -> `pass`, stdout DONE, no PASS-UAT |
| BT0x7 | attempts exhausted -> `fail` |
| BT0x8 | `Start-BobBuildLoop -Once -TestWorld` does not call live gh / live bridge |

## Done when

Acceptance in the FR is true in the tree. Test-Pack green off-DEV. Open a
PR. Do not stamp UAT.
