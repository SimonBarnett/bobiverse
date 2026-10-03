<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-pr-mrb-cursor-models-transaction-2026-09-20.md, last changed 2026-09-20. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: PR/MRB Cursor Models transaction

**Date:** 2026-09-20
**Spec:** `docs/feature-request-pr-mrb-cursor-models-transaction-2026-09-20.md`
**Chair:** Bob

## This pass (docs + skills + packet contract)

1. Park the FR. Update README mermaid, `bob-build-loop` mermaid, MRB/dispatch
   skills, `docs/mrb.md`, harvest log.
2. `config/default.json` `models.mrbCursor` = Cursor Grok `grok-4.6` (not
   Other Models). `Get-BobJobModel` fallback matches. Test-Pack BT0p.
3. Worker packets: open a PR; never push main; never merge. MRB packets:
   PASS-nits merge; FAIL do not merge.
4. `tools/Test-Pack.ps1` green off-DEV.
5. Copy `.grok/skills` to `~\.grok\skills`. Open a PR for this change.

## Follow-up (meter fetch)

`Get-CursorAgentUsage.py` still reads Grok Bot Sand. Tray top bar and
`Get-BobCapacity.cursor_models.remaining_pct` must become the Spending
Cursor Models remaining % (20 Sep 2026: 1% used, not Sand overage). Do not
invent a number. Separate FR if this pass does not land the fetch.

## Done when

Acceptance in the FR is true in the tree. Bob MRBs the PR. Do not stamp UAT.
