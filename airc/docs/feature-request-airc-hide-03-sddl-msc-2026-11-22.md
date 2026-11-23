# Feature request: Apply SO Services.msc hide SDDL to Airc

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE-03`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Depends-on:** #9128, #9130  
**Skill:** visionary  
**Park:** park-only (no bob-job-loop until digest unhold)

## Objective

Deliver exactly one acceptance slice: after native register, apply the Stack Overflow **hide SDDL** via `sc.exe sdset Airc` so **`Airc` does not appear in Services.msc** for elevated Administrators, while the service stays Running and controllable via AIRC-HIDE-01.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Hidden in Services.msc; still Running | After install/upgrade, `services.msc` list has no Airc row; helper reports Running | Open `services.msc` and confirm no Airc row; run AIRC-HIDE-01 helper status (or `sc.exe sdshow Airc`) and confirm Running | Airc listed in MMC, or service Stopped/uncontrollable after sdset |

LOCKED

## Shape

Primary: service

LOCKED

## Stack

Default: `sc.exe sdset` with LOCKED SO SDDL string; apply in `Install-Airc` after service create/config; idempotent on upgrade.

Why: matches operator-cited SO answer; no Type= hacks.

Why-not: registry DisplayName blanking alone; driver tricks.

LOCKED

## Architecture

```
native CreateService (AIRC-HIDE-02)
  -> sc sdset Airc <hide-SDDL>
  -> AIRC-HIDE-01 status == Running
MMC EnumServicesStatus as admin: Airc absent
```

Hide SDDL:

```text
D:(D;;DCLCWPDTSD;;;IU)(D;;DCLCWPDTSD;;;SU)(D;;DCLCWPDTSD;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)
```

Ref: https://stackoverflow.com/questions/25736268/how-to-register-a-windows-service-but-avoid-it-being-listed-in-the-services-cons

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap

Service is fully visible in Services.msc today.

## Out of scope

- Task Manager true hide
- Hiding other bobiverse services

## LOCKED

- One acceptance row only
- Full SO hide (BA included)
- Fail install if sdset non-zero

## UNKNOWN

- (none)
