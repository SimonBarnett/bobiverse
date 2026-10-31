# Feature request: Airc EXTENSION — Priority web force-install (GPO + registry fallback)

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-143743`  
**Decisions locked:** operator MC cards 2026-10-31

Related: `airc/VISION.md`, DCC bulk FR #5003 / #5008, remote-control verb model (STATUS / UPDATE), UPDATE cap FR #3287 / #3764.

## Objective

LOCKED: An authorized remote **`EXTENSION install`** on `{mid}_console` force-installs the Priority web extension (`cgmpadejahkaggjpffnhaoiafbnicgpa`) for **Chrome and Edge** across the customer domain — **DC + GPO** via `Set-GPRegistryValue` / `New-GPO`, then **always** LDAP AD computer enum + per-host registry / local policy to **fill holes** on reachable hosts — while the install worker runs **isolated** from the Airc service process and returns a **DCC** (or CONT fallback) log including every failure; optional **`-WhatIf`** dry-run; auth same as **UPDATE** (ops/half-ops; `update=off` blocks EXTENSION).

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | EXTENSION verb | Authorized `EXTENSION install` [optional `-WhatIf`] accepted; unauthorized / `update=off` → existing UPDATE-style auth exits | Wire tests; skills document verb | No verb; agents hand-edit GPO only; WhatIf writes policy |
| S2 | GPO happy path | When a DC is reachable and caller has rights, worker finds DC and uses **PowerShell GroupPolicy** (`New-GPO` / `Set-GPRegistryValue` as needed) to set ForceInstall for id + **Chrome Web Store update URL** on **Chrome and Edge** domain policy | Lab/domain test: GPO ExtensionInstallForcelist contains `cgmpadejahkaggjpffnhaoiafbnicgpa;https://clients2.google.com/service/update2/crx` for both products | DC reachable but only one browser; silent no-op |
| S3 | Fill-holes fallback | **After** GPO attempt (success or fail), enumerate **AD computer objects (LDAP)** and apply local/registry ForceInstall on each **reachable** host still missing coverage (Chrome + Edge); machine account first, **CredMan fallback** on access-denied when configured | Lab: after EXTENSION, hole hosts get registry keys; access-denied without CredMan logged as failure; with CredMan succeeds | Skips fallback when GPO ok; invents non-AD hosts; password on IRC |
| S3b | gpupdate | After GPO write, **best-effort** `gpupdate /force` on reachable hosts; log per-host gpupdate failures (do not require wait-until-applied) | Log shows gpupdate attempted; failures listed; DONE not blocked on full domain refresh | No refresh attempt; hung wait forever for all hosts |
| S4 | Isolation | EXTENSION work runs in a **detached / child worker** — never AD/GPO/registry loops on the IRC receive thread; worker faults must not crash or stop service `Airc` | Fault-injection: worker exception → service still Running + DONE/err | GPO on message handler; service Stopped after bad EXTENSION |
| S5 | DCC log + failures | Structured log (GPO, hosts, fill-holes, gpupdate, every failure) via reverse **DCC** when `DCCLISTEN` offered, else IRC CONT; short IRC summary includes failure counts | Harness with/without DCCLISTEN | Failures only local; PRIVMSG flood of full log |
| S6 | Extension id + update URL | Default id `cgmpadejahkaggjpffnhaoiafbnicgpa`; ForceInstall update URL **`https://clients2.google.com/service/update2/crx`** for **both** Chrome and Edge policy trees | Config/example + tests | Missing default; different undocumented URLs without config |
| S7 | Secrets / blast radius | No domain passwords on IRC; machine account first; optional CredMan for remote registry only; no secrets in DCC/intake | Redaction tests | Password in EXTENSION args or DCC log |
| S8 | Auth = UPDATE | Same ops/half-ops gate as UPDATE; **`update=off` also refuses EXTENSION** | Cap matrix tests | EXTENSION works when update=off; arbitrary bob-* |

LOCKED.

## Shape

Primary: **service** (new Airc console verb + isolated worker).

LOCKED

## Stack

Default: Airc console `EXTENSION install` [-WhatIf] → **detached worker** (PowerShell) → **GroupPolicy** module (`New-GPO` / `Set-GPRegistryValue`) for Chrome + Edge `ExtensionInstallForcelist` → LDAP AD computer enum → per-host registry/local policy (machine account, then CredMan) → best-effort remote `gpupdate /force` → reverse DCC for log bytes.

ForceInstall entry shape: `cgmpadejahkaggjpffnhaoiafbnicgpa;https://clients2.google.com/service/update2/crx`

Why: Matches fleet remote-control wire, UPDATE isolation + UPDATE auth reuse, Chromium enterprise force-install.

Why-not: GPMC-COM-only; backup-modify-import as primary; IRC-thread GPO; separate ExtensionInstaller.exe; fallback-only-when-GPO-fails (holes after successful GPO would remain).

LOCKED

## Architecture

```
Operator/agent
  [optional] DCCLISTEN id=… host=… port=… token=…
  PRIVMSG {mid}_console :EXTENSION install [-WhatIf]
       |
       v
Airc service (live)
  - auth: same as UPDATE (+o/+h); update=off => refuse
  - reply accepted / start job
  - spawn ISOLATED worker
       |
       v
EXTENSION worker (isolated)
  1) Find DC + New-GPO/Set-GPRegistryValue ForceInstall
     Chrome+Edge, id+https://clients2.google.com/service/update2/crx
  2) ALWAYS then: LDAP enum computers → fill holes via registry/local policy
     (machine account; CredMan on access-denied if configured)
  3) Best-effort gpupdate /force on reachable hosts
  4) Structured log (ok/fail per step/host); -WhatIf skips writes
       |
       v
Airc replies
  - short IRC summary + DONE exit=
  - full log via DCC (or CONT) including failures
```

LOCKED for Phase 0.

## Screens

None. Mocks out of scope.

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| EXTENSION verb | Absent | `EXTENSION install` [-WhatIf] + UPDATE-equivalent auth |
| GPO | Absent | DC + Set-GPRegistryValue/New-GPO Chrome+Edge |
| Fill-holes | Absent | Always-after-GPO LDAP + registry; machine then CredMan |
| gpupdate | Absent | Best-effort remote `/force` |
| Isolation | UPDATE detached | Same class for EXTENSION |
| DCC | Shell bulk FR #5003 | EXTENSION job log via DCCLISTEN |
| Extension id / URL | Not in product | Pin id + Chrome Web Store update URL |

## LOCKED

- Repo `SimonBarnett/bobiverse`; product `airc/`
- Grammar: `EXTENSION install` with optional `-WhatIf` only (no browser filter flags in MVP)
- Default extension id `cgmpadejahkaggjpffnhaoiafbnicgpa`
- Update URL for both browsers: `https://clients2.google.com/service/update2/crx`
- GPO via PowerShell GroupPolicy (`New-GPO` / `Set-GPRegistryValue`)
- Fallback **always after GPO** to fill holes (LDAP AD computers + local/registry)
- Per-host auth: machine account first, CredMan fallback
- Auth/cap: same as UPDATE; `update=off` blocks EXTENSION
- After GPO: trigger `gpupdate /force` on reachable hosts (best-effort, log failures)
- Isolated worker; DCC log including failures
- Chrome + Edge

## UNKNOWN

- Exact CredMan target name/schema for optional domain account (when machine account denied)
- Which GPO name/OU linkage is default when creating vs updating an existing Priority/airc GPO
- Whether `-WhatIf` still runs LDAP discovery (read-only) or skips enum entirely
- LGPO.exe vs raw registry on workgroup-joined / non-domain reachable hosts inside AD enum results (edge case)

## Implementation slices

See `drafts/backlog.md` (#5290–#5295).
