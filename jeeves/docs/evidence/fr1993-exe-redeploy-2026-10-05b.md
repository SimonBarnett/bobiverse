# FR #1993 live exe tip redeploy evidence (2026-10-05b)

Seat: `win-mpre8vi4u6u` (DIGEST_ID_FOLD of `ionos`). Living FR stays open (`Refs` only — never `Closes`).

## Why

Prior tip redeploy (#2485 @ `14a6549`) landed before chair merges that must live inside frozen `jeeves.exe`:

- FR #2464 / PR #2469 — `mrb-fail` remediation offerable
- FR #2451 / PR #2468 — `require_machine=ionos` for install(+smoke) on ionos

Tip advanced to `a8b96b0` (`a8b96b0819fd7d4e528900bba508ca8da5ff1083`).

## What we did

1. Backed up prior exe/NSSM under `C:\ai\jeeves-exe-build\backup-before-1993-redeploy-2026-10-05b\`.
2. Built via `jeeves/scripts/Build-Jeeves.ps1` from `origin/main` @ `a8b96b0`. Build smoke exit 0.
3. Stopped **ircJeeves only** (BobIrcd untouched). Replaced `C:\ai\jeeves-exe-build\jeeves.exe` (~12.9 MB). Started ircJeeves.

## Post-redeploy checks

| Check | Result |
|-------|--------|
| Service | `ircJeeves` Running; `BobIrcd` Running |
| E1 LISTEN | `127.0.0.1:7700` LISTENING |
| E2 local intake | POST `/bob/v1/intake` with `probe-shape-only-do-not-file` → **202** `queued:true` |
| E4 smoke | `--self-test --check imports` → **exit 0** |

## Still open on living #1993

- Public ARR 30-post intake storm
- Full `--self-test` in a maintenance window
- Heal re-offer of living umbrella after dual GIVEUP (see #2486)

Ergo / `BobIrcd` untouched.
