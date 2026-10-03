# FR #1016 — ionos live chair/queue reliability evidence

**Seat:** win-mpre8vi4u6u-20596 on WIN-MPRE8VI4U6U (ionos / Ergo+ircJeeves host)
**Date:** 2026-10-03
**main tip verified:** `3f364d9` (includes #1122 needs-mrb1 / per-seat cooldown / focus fallback + #1135 tests)

## Acceptance

| Criterion | Result | Evidence |
|-----------|--------|----------|
| Live ionos chair on merged skip rules | PASS | Hotpatched `C:\ai\jeeves\scripts\gitclaim.py` to `origin/main` SHA256 match; `Restart-Service ircJeeves`; restarted scheduled task `BobCallback`. Services Running; chair `+o`. |
| No per-PR UAT offers | PASS | Live queue: `unaccepted` UAT count **0**, `accepted` UAT count **0**. Unit: poisoned `UAT #977` alone → `offer_focus_top` **empty**; with repo UAT `#0` → offers `#0` only (`GATE_OK`). |
| Queue-status observable | PASS | `worker.log` shows `relay: injected FROM Jeeves ... nothing queued` at 20:53:53Z and 21:29:56Z; `last-from.txt` updated on inject. PR #1004 (FR #994) already merged. |
| Regression tests | PASS | `pytest jeeves/tests/test_fr1080_needs_mrb1_offer.py jeeves/tests/test_fr635_uat_implementer_pr_enrich.py -q` → **6 passed** on main worktree. |

## Child issues (already closed; folded into this FR)

- #610 mrb-home skip — closed; gates on main
- #971 / #978 per-PR UAT — closed; t853u + live prune/hotpatch
- #996 nothing-queued visibility — closed; #1004 + live inject logs

## Could not / notes

- Jeeves install git worktree is on branch `fix/resync-paginate-open-issues` (not `main`); start-up sync ff-only skipped. Flat `scripts/gitclaim.py` was hotpatched to main tip so live behaviour matches main. Follow-up: get install worktree onto `main` so robocopy cannot drift.
- Public intake webhook may still return 404/502 intermittently (separate #1040/#1047 class).

## Ops commands used (no secrets)

```powershell
Restart-Service ircJeeves -Force
Stop-ScheduledTask BobCallback; Start-ScheduledTask BobCallback
Get-Service ircJeeves; Get-ScheduledTask BobCallback
```