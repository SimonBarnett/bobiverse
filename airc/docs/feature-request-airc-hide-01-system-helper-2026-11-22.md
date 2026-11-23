# Feature request: SYSTEM status/control helper for Airc

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE-01`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Depends-on:** #9128  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until digest unhold)

## Objective

Deliver exactly one acceptance slice: a **SYSTEM-capable** helper that can report Running/Stopped and start/stop/restart service **`Airc`** when an elevated Administrator `Get-Service Airc` would Access Denied after the SO hide SDDL.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Helper controls Airc under restricted DACL | Helper reports state and can start/stop/restart when BA Get-Service fails Access Denied | Unit/integration on lab after hide SDDL or mocked Access Denied; script exit 0 | Helper uses only Get-Service; fails when BA query denied |

LOCKED

## Shape

Primary: service

Hybrid note: PowerShell/common script helper used by install and fleet ops; not a website.

LOCKED

## Stack

Default: PowerShell on Windows; SCM APIs / `sc.exe` / service handle opened with rights that work as SYSTEM (or documented elevation to SYSTEM). Existing bobiverse common scripts tree.

Why: fleet already ships PowerShell service helpers.

Why-not: require Operators to use Services.msc (hidden after later FR).

LOCKED

## Architecture

```
Install / Update / Recover / Restart
  -> Invoke-AircServiceControl (name TBD)
       -> SYSTEM or sufficient SCM rights
       -> status | start | stop | restart for service Airc
Never assume BA Get-Service succeeds after hide SDDL.
```

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

After SO `sc sdset` hide, Administrators lose QUERY_STATUS/STOP on `Airc`. Current scripts call `Get-Service Airc` and will strand upgrades.

## Out of scope

- Applying the hide SDDL (AIRC-HIDE-03)
- Native host cutover (AIRC-HIDE-02)
- Task Manager process hide

## LOCKED

- One acceptance row only
- Service name `Airc` only

## UNKNOWN

- Exact elevation mechanism (scheduled task SYSTEM vs existing PsExec deploy vs OpenSCManager as SYSTEM token) — implementer picks smallest durable option and documents it
