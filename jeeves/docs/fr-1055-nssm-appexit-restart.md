# FR #1055 — ircJeeves graceful quit must Restart (NSSM AppExit 0)

**Seat:** win-mpre8vi4u6u-20596 on WIN-MPRE8VI4U6U (ionos)
**Date:** 2026-10-03

## Root cause

`Start-Jeeves.ps1` ends with `exit $LASTEXITCODE` after the chair python process. A graceful quit yields **exit 0**. Install only set `AppExit Default Restart` and did **not** explicitly set `AppExit 0 Restart`. When exit 0 was treated as a successful stop (or overridden), NSSM left **ircJeeves Stopped** instead of bringing the chair back.

## Fix

1. `Set-BobiverseNssmAppExitRestart` in `Bobiverse-Common.ps1` — sets Default=Restart, **0=Restart**, AppRestartDelay=2000
2. `Install-Jeeves.ps1` / `Install-Bob.ps1` call the helper
3. `Update-BobiverseService.ps1` Apply re-pins after MSI
4. `Assert-BobJeevesNssmRestart.ps1` — smoke for live ionos

## Live apply (this seat)

Applied helper against running `ircJeeves`; assert PASS; service Status=Running.