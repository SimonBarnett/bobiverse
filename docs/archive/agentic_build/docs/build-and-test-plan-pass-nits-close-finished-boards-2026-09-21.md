<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-pass-nits-close-finished-boards-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: PASS-nits close finished boards (#118)

**Date:** 2026-09-21
**Spec:** `docs/feature-request-pass-nits-close-finished-boards-2026-09-21.md`
**Chair:** Bob

## Goals

After PASS-nits **merge succeeds**, close the feature-request issue, every
prior FAIL MRB board for that FR, and the PASS-nits board. Each close
comment links the merged PR. The MRB worker does this; the loop driver
calls `Close-BobBuildLoopFinished` on PASS-nits if the worker skipped a
step. Fail closed: no `DONE` when `gh` is missing, merge fails, or any
close fails.

## Tree

| Path | Role |
|---|---|
| `tools/Bob-BuildLoop.ps1` | `Get-BobPassNitsClosePayload`, `Invoke-BobPassNitsFinish`, `Close-BobBuildLoopFinished` |
| `tools/Start-BobBuildLoop.ps1` | PASS-nits terminal calls finish before stdout `DONE` |
| `.grok/skills/bob-hostile-mrb` | Worker merge + close ritual |
| `tests/fixtures/Fake-Gh.ps1` | `pr view`, `pr merge`, `issue close` for Test-Pack |
| `tools/Test-Pack.ps1` BT118* | Payload + finish off-DEV |

## Test IDs

| ID | Assert |
|---|---|
| BT118a | First-try PASS payload: FR + PASS only; comment names PR URL |
| BT118b | Two FAIL passes + PASS payload lists all three FAIL numbers + FR + PASS |
| BT118c | Fake-Gh `merge-fail`: finish `ok=$false`; no issue close logged |
| BT118d | Fake-Gh missing: finish `ok=$false`; message mentions gh |
| BT118e | Loop `-Once -TestWorld` PASS uses `-TestPassNitsFinish`; no live gh |

## Done when

Acceptance in the FR is true. Test-Pack green off-DEV. Open a PR titled
with `#118`. Do not stamp UAT.
