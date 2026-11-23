# Feature request: Fleet scripts off Get-Service Airc / NSSM

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE-04`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Depends-on:** #9128, #9129, #9130  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until digest unhold)

## Objective

Deliver exactly one acceptance slice: **Update-Bobiverse / Recover / Restart / install verify / uninstall** paths for product **airc** use the AIRC-HIDE-01 helper and **native SCM**, with **no NSSM dependency** required to manage service `Airc`.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Fleet airc control without Get-Service/NSSM | airc product paths in common+airc scripts use helper + native SCM; no required nssm.exe for start/stop/status/uninstall of Airc | Grep + lab upgrade/restart after hide | Update/Recover/Restart/uninstall still require nssm or bare Get-Service Airc as the only path |

LOCKED

## Shape

Primary: service

LOCKED

## Stack

Default: existing `common/scripts/*Bobiverse*Service*.ps1` and `airc/scripts/Install-Airc*.ps1` / `Uninstall-Airc.ps1`.

Why: those are the live fleet call sites.

Why-not: leave Get-Service and hope MMC stays.

LOCKED

## Architecture

```
Update-BobiverseService -Product airc
Recover-BobiverseService / Restart-BobService Airc
Install-Airc verify / Uninstall-Airc
  -> AIRC-HIDE-01 helper + native SCM
  -> not nssm.exe, not BA Get-Service alone
```

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

Scripts assume visible service + NSSM remove/install.

## Out of scope

- Applying sdset (03)
- Docs/skills prose (05)
- Bob/Jeeves service helpers beyond shared code needed for airc

## LOCKED

- One acceptance row only
- Airc product only

## UNKNOWN

- Whether shared helpers gain an `-Product airc` branch only or a generic SYSTEM control used later by other products (prefer airc-first smallest change)
