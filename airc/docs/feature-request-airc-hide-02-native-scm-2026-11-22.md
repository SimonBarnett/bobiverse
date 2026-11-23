# Feature request: Native SCM host for Airc — no NSSM

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE-02`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Depends-on:** #9128, #9129  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until digest unhold)

## Objective

Deliver exactly one acceptance slice: install registers **`Airc`** as a native **`SERVICE_WIN32_OWN_PROCESS`** with **`airc.exe`** as binPath so **runtime does not require `nssm.exe`**. Preserve LocalSystem, auto-start, restart-on-failure parity (or document intentional deltas), and install log path behaviour. `{mid}_console` still answers.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Native host, no nssm runtime | After install/upgrade, `Airc` Running via airc.exe SCM host; no nssm.exe required; console nick answers probe | Install lab; process list has no nssm hosting Airc; STATUS/probe OK | Install still calls nssm install/set as required path; nssm.exe hosts Airc |

LOCKED

## Shape

Primary: service

LOCKED

## Stack

Default: `airc.exe` with in-process SCM control handler (preferred) or smallest owned wrapper **not named nssm.exe**. `sc.exe` create + failure actions. Prefer in-process in `airc.exe`.

Why: removes nssm from Task Manager for this product.

Why-not: keep NSSM; impersonate Microsoft binary names.

LOCKED

## Architecture

```
Install-Airc
  -> (remove/replace NSSM-registered Airc if present)
  -> CreateService Airc binPath=airc.exe [args]
  -> LocalSystem, SERVICE_AUTO_START, failure actions (restart)
  -> AIRC-HIDE-01 helper verifies Running
airc.exe handles SERVICE_CONTROL_STOP / shutdown
```

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

NSSM is the current Application host; Task Manager shows nssm.exe. Console restart semantics are NSSM AppExit Restart.

## Out of scope

- SO Services.msc hide SDDL (AIRC-HIDE-03)
- Deleting nssm from the MSI tree (optional follow-up; this FR only requires install/runtime not to need it)
- Renaming airc.exe

## LOCKED

- One acceptance row only
- airc.exe may appear in Task Manager
- Depends on AIRC-HIDE-01 for verify/control after register

## UNKNOWN

- Failure-actions delay vs NSSM AppRestartDelay=5000 exact match
