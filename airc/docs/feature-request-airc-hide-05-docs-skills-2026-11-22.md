# Feature request: Docs + skills + VISION for Airc MMC hide / no nssm

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE-05`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Depends-on:** #9128, #9131, #9132  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until digest unhold)

## Objective

Deliver exactly one acceptance slice: update **VISION**, **bobiverse-airc** / troubleshooting skills, and ops docs so operators measure S1 without `Get-Service` in MMC, know **Services.msc hide**, **no nssm**, **`airc.exe` may show in Task Manager**, and **true Task Manager hide is out of scope**.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Docs/skills match shipped behaviour | VISION S1 measure + airc skills/ops docs describe helper status, MMC hide, no nssm, airc.exe OK in Task Manager, true TM hide out of scope | Grep/read VISION + `.grok/skills/bobiverse-airc*` + airc-ops | Docs still say Get-Service Airc as sole S1 or document nssm as required host |

LOCKED

## Shape

Primary: service

LOCKED

## Stack

Default: markdown under `airc/` and `airc/.grok/skills/` (and shared pointers if any).

Why: operators and MRB use VISION + skills as SoT.

Why-not: leave VISION claiming Get-Service after hide lands.

LOCKED

## Architecture

```
VISION S1 how-measured -> AIRC-HIDE-01 helper (not Get-Service alone)
bobiverse-airc / troubleshooting -> MMC hide SDDL, native host, Task Manager notes
airc-ops.md -> install/upgrade expectations
```

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

VISION and skills describe NSSM `Airc` and `Get-Service Airc`.

## Out of scope

- Code paths (01–04)
- Hiding Bob/Jeeves docs

## LOCKED

- One acceptance row only
- Cite SO link for MMC hide

## UNKNOWN

- (none)
