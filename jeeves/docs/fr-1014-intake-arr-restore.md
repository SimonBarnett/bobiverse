# FR #1014 — intake ARR 502.3 restore (ionos)

**Seat:** win-mpre8vi4u6u-20596 on WIN-MPRE8VI4U6U (ionos)
**Date:** 2026-10-03

## Root cause

IIS site `irc-ntsa` (`C:\inetpub\irc-ntsa\web.config`) rewrites `^bob/v1/intake(.*)` to `http://127.0.0.1:7700/bob/v1/intake{R:1}`. When **BobCallback** is not listening on `:7700`, ARR returns **502.3** / `0x80072efd` (connection with the server could not be established). Fleet seats then KEEP harvest/intake offline.

Chair logs showed intermittent `webhook-health local DOWN` / recover after 12–18 minutes around the failure window.

## Restore evidence

| Check | Result |
|-------|--------|
| BobCallback | Scheduled task **Running**; python listening `127.0.0.1:7700` |
| Local POST `/bob/v1/intake` | **HTTP 202** via `Report-BobiverseIntakeIssue.ps1` (`intake_id=in_1c16def2537f4904`) |
| Public POST `https://irc.ntsa.uk/bob/v1/intake` | **HTTP 202** (same script path) |
| Flush | `Invoke-BobiverseHarvest.ps1 -Flush` → `sent=0 kept=0` (queue drained) |
| Health semantics | `intake=404` on GET `/bob/v1/intake/jeeves-health-probe` counts as **UP** in `chair_health.CHECKS` |

## Code changes in this PR

1. `Start-Jeeves.ps1` — prefer scheduled task `BobCallback`, wait up to 20s for listen, warn if ARR would 502.3.
2. `Assert-BobIntakeLocal.ps1` — POST local (+ public) intake, expect 202.

## Ops

```powershell
Get-ScheduledTask BobCallback
Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 7700 -State Listen
.\scripts\Assert-BobIntakeLocal.ps1
.\scripts\Invoke-BobiverseHarvest.ps1 -Flush
```