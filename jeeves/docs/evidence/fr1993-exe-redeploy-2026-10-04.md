# FR #1993 live exe redeploy evidence (2026-10-04 evening)

Seat: `win-mpre8vi4u6u` (DIGEST_ID_FOLD of `ionos`). Living FR stays open (`Refs` only).

## Why

Live chair still emitted empty replies without seat-relative `for you` wording after #2335 merged on git tip. Runtime `C:\ai\jeeves-exe-build\jeeves.exe` was stale vs `origin/main` @ `0c6b131` (merge of #2335).

## What we did

1. Backed up NSSM Application/AppParameters/AppDirectory and prior `jeeves.exe` under `C:\ai\jeeves-exe-build\backup-before-1993-redeploy\`.
2. Built from worktree on `origin/main` via `jeeves/scripts/Build-Jeeves.ps1` (PyInstaller onefile). Smoke `--self-test --check imports` exit 0 during build.
3. Stopped **ircJeeves only** (never BobIrcd / Ergo). Replaced `C:\ai\jeeves-exe-build\jeeves.exe`. Started ircJeeves.
4. Left worker seats alone.

## Post-redeploy checks

| Check | Result |
|-------|--------|
| Service | `ircJeeves` Running |
| E1 LISTEN | Exactly one `127.0.0.1:7700` LISTENING (PyInstaller parent+child processes expected) |
| E2 local intake | `POST http://127.0.0.1:7700/bob/v1/intake` → **202** `queued:true` |
| E4 smoke | `jeeves.exe --self-test --check imports --home <temp>` → **exit 0** `ok:true` (not full self-test while service owns :7700) |
| BobCallback task | Remains Disabled |
| WP4 offline storm | seed=1, 50/50, `ok=true`, `failures=[]`, `inproc_lock=true` → `fr1993-wp4-storm-after-redeploy.json` |

## Tip baked into exe

Includes seat-relative empty wording (`N offerable for you under focus`, FR #2333 / PR #2335) and sticky no-ACK caps (FR #2309 / PR #2330).

## Still open on living #1993

- Public ARR 30-post intake storm (E2 public path)
- Full `--self-test` in a maintenance window (no :7700 contention)
- Optional live-digest-home storm after a quiet ops window

Ergo / `BobIrcd` untouched.
