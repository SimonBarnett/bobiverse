# FR #1993 live exe tip redeploy evidence (2026-10-05)

Seat: `win-mpre8vi4u6u` (DIGEST_ID_FOLD of `ionos`). Living FR stays open (`Refs` only — never `Closes`).

## Why

Live `C:\ai\jeeves-exe-build\jeeves.exe` mtime was 2026-10-05T06:53:34Z while `origin/main` advanced through empty-offer heal (#2450), docs (#2457/#2459), Clear-worktrees StrictMode (#2462), and later tips. Chair product merges need an exe rebuild + ircJeeves-only recycle to take effect.

## What we did

1. Backed up NSSM Application/AppParameters/AppDirectory and prior `jeeves.exe` under `C:\ai\jeeves-exe-build\backup-before-1993-redeploy-2026-10-05\`.
2. Built from worktree on `origin/main` @ `14a6549` (`14a65492797d414dfb054aca786506bc50e7a1e2`) via `jeeves/scripts/Build-Jeeves.ps1` (PyInstaller onefile). Build smoke `--self-test` exit 0.
3. Stopped **ircJeeves only** (never BobIrcd / Ergo). Replaced `C:\ai\jeeves-exe-build\jeeves.exe` (13.5 MB). Started ircJeeves.
4. Left worker seats / tray alone.

## Post-redeploy checks

| Check | Result |
|-------|--------|
| Service | `ircJeeves` Running |
| E1 LISTEN | Exactly one `127.0.0.1:7700` LISTENING (PID observed) |
| E2 local intake | `POST http://127.0.0.1:7700/bob/v1/intake` with `probe-shape-only-do-not-file` → **202** `queued:true` |
| E4 smoke | copy of new exe `--self-test --check imports --home <temp>` → **exit 0** |
| BobCallback task | left as previously configured (Disabled path from cutover) |
| BobIrcd | Running — untouched |

## Tip baked into exe

Includes pin+ledger empty-offer heal (FR #2446 / PR #2450), StrictMode Clear-worktrees stringify (FR #2460 / PR #2462), and prior WP0–WP4 chair+HTTP+self-test/heal surface.

## Still open on living #1993

- Public ARR 30-post intake storm (E2 public path)
- Full `--self-test` in a maintenance window (no :7700 contention)
- Living umbrella remains tracking — child WP3/WP4/#2352 already CLOSED

Ergo / `BobIrcd` untouched.
