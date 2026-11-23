# Feature request theme: Hide Airc from Services.msc + native host (no nssm)

**Repo:** `SimonBarnett/bobiverse`  
**ID:** `AIRC-HIDE`  
**Date:** 2026-11-22  
**Theme:** Airc console SCM visibility + host process  
**Skill:** visionary  
**Park:** park-only (fr-digest + hold; no bob-job-loop until digest unhold)  
**Index:** `airc/docs/fr-index-airc-hide-services-msc-2026-11-22.md`  
**Digest:** [#9128](https://github.com/SimonBarnett/bobiverse/issues/9128)

## Objective

Service **`Airc`** must not appear in **Services.msc** (even for elevated Administrators), using the Stack Overflow service-DACL pattern. Runtime must not require **`nssm.exe`** so Task Manager no longer shows an nssm host row. **`airc.exe` may remain visible** in Task Manager. True “not listed at all” Task Manager hide is out of scope.

LOCKED

## Success

Theme contract — delivered by child FRs:

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| T1 | Hidden in Services.msc | `Airc` absent from MMC services list for elevated admin | Lab: open `services.msc` after install/upgrade | `Airc` / airc console display name listed |
| T2 | No nssm.exe for Airc | Airc runs as native own-process SCM host; no nssm.exe required at runtime | Process list / install path; no nssm Application for `Airc` | nssm.exe hosts Airc or install requires nssm |
| T3 | Fleet control still works | Start/stop/status/restart work when BA `Get-Service` Access Denied | Helper + Update/Recover/Restart/install verify | Box stranded Stopped; only MMC path worked before |

Child FRs each own one S1 row; theme table is the batch contract.

LOCKED

## Shape

Primary: **service**

Hybrid note: Windows SCM + install scripts; IRC `{mid}_console` behaviour unchanged. No website/app UI.

LOCKED

## Stack

Default: existing bobiverse airc (frozen `airc.exe` / Python console), PowerShell install (`Install-Airc.ps1`), `sc.exe` for create/sdset/failure actions. Prefer SCM control handler **inside `airc.exe`**.

Why: smallest path to MMC hide + drop nssm without a second product binary named like Microsoft hosts.

Why-not: NSSM forever; kernel/DKOM Task Manager hide; renaming to `svchost.exe`.

LOCKED

## Architecture

```
Install-Airc
  -> native CreateService Airc (binPath=airc.exe, LocalSystem, auto-start, failure actions)
  -> sc sdset Airc <SO-hide-SDDL>     # Services.msc enumeration drops Airc
  -> SYSTEM helper for status/start/stop/restart

Task Manager: airc.exe OK; nssm.exe must not host Airc
True Task Manager hide: OUT OF SCOPE
```

SO hide SDDL (LOCKED reference):

```text
D:(D;;DCLCWPDTSD;;;IU)(D;;DCLCWPDTSD;;;SU)(D;;DCLCWPDTSD;;;BA)(A;;CCLCSWLOCRRC;;;IU)(A;;CCLCSWLOCRRC;;;SU)(A;;CCLCSWRPWPDTLOCRRC;;;SY)(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)
```

Source: https://stackoverflow.com/questions/25736268/how-to-register-a-windows-service-but-avoid-it-being-listed-in-the-services-cons

LOCKED

## Screens

No new product UI.

| id | file | state |
|----|------|-------|
| M1 | (n/a) | n/a |

## Gap vs current tree

- `Install-Airc` / `Install-AircConsole` register via **NSSM**; Task Manager shows **nssm.exe**.
- Service is visible in **Services.msc** under DisplayName like `airc console (#mid IRC shell)`.
- Fleet scripts use `Get-Service Airc`, which breaks after SO hide for Administrators.

## Out of scope

- True Task Manager hide (process not listed at all)
- Renaming `airc.exe` away from airc
- Hiding `ircBob` / `ircJeeves` / `BobIrcd`
- Kernel drivers / DKOM / unsigned rootkit techniques

## LOCKED

- Airc only; SO full MMC hide; no nssm at runtime; airc.exe may show in Task Manager
- Park via fr-digest + Depends-on children; unhold digest to release
- One acceptance row per child issue

## UNKNOWN

- Exact failure-actions timings vs today’s NSSM AppRestartDelay=5000 (implementer documents parity or intentional delta in AIRC-HIDE-02)
- Whether bundled `third_party\nssm` is deleted from the MSI in this batch or a follow-up pack FR (02 only requires install/runtime not to use it)
