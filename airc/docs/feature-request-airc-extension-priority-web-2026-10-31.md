# Feature request: Airc EXTENSION - Priority web force-install (GPO + registry fallback)

**Repo:** `SimonBarnett/bobiverse` 
**Product path:** `airc/` 
**Date:** 2026-10-31 
**Plan folder:** `bob/plan/work/plan-20261031-143743` 
**Decisions locked:** operator MC cards 2026-10-31

Related: `airc/VISION.md`, DCC bulk FR #5003 / #5008, remote-control verb model (STATUS / UPDATE), UPDATE cap FR #3287 / #3764.

## Objective

LOCKED: An authorized remote **`EXTENSION install`** on `{mid}_console` force-installs the Priority web extension (`cgmpadejahkaggjpffnhaoiafbnicgpa`) for **Chrome and Edge** across the customer domain - **DC + GPO** via `Set-GPRegistryValue` / `New-GPO`, then **always** LDAP AD computer enum + per-host registry / local policy to **fill holes** on reachable hosts - while the install worker runs **isolated** from the Airc service process and returns a **DCC** (or CONT fallback) log including every failure; optional **`-WhatIf`** dry-run; auth same as **UPDATE** (ops/half-ops; `update=off` blocks EXTENSION).

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | EXTENSION verb | Authorized `EXTENSION install` [optional `-WhatIf`] accepted; unauthorized / `update=off` -> existing UPDATE-style auth exits; `-WhatIf` returns full read-only plan (DC/GPO inspect + LDAP + hole list) with **zero writes** | Wire tests; skills document verb | No verb; WhatIf writes GPO/registry/gpupdate |
| S2 | GPO happy path | When a DC is reachable and caller has rights, worker finds DC and uses **PowerShell GroupPolicy** to create/update GPO **`Priority-web-extension`** (link **domain root**) with ForceInstall for id + Chrome Web Store update URL on **Chrome and Edge** | Lab: named GPO linked at domain root; ExtensionInstallForcelist contains `cgmpadejahkaggjpffnhaoiafbnicgpa;https://clients2.google.com/service/update2/crx` for both products | Wrong GPO name; not linked; only one browser |
| S3 | Fill-holes fallback | **After** GPO attempt, LDAP enum AD computers; apply **raw remote registry** ForceInstall on reachable hosts still missing coverage (Chrome + Edge); machine account first, CredMan **`PriorityAirc/ExtensionAdmin`** on access-denied; no LGPO.exe | Lab: hole hosts get registry keys; missing CredMan -> logged failure; workgroup-style targets use raw registry only | Skips fallback when GPO ok; invents non-AD hosts; uses LGPO.exe |
| S3b | gpupdate | After GPO write, **best-effort** `gpupdate /force` on reachable hosts; log per-host gpupdate failures (do not require wait-until-applied) | Log shows gpupdate attempted; failures listed; DONE not blocked on full domain refresh | No refresh attempt; hung wait forever for all hosts |
| S4 | Isolation | EXTENSION work runs in a **detached / child worker** - never AD/GPO/registry loops on the IRC receive thread; worker faults must not crash or stop service `Airc` | Fault-injection: worker exception -> service still Running + DONE/err | GPO on message handler; service Stopped after bad EXTENSION |
| S5 | DCC log + failures | Structured log (GPO, hosts, fill-holes, gpupdate, every failure) via reverse **DCC** when `DCCLISTEN` offered, else IRC CONT; short IRC summary includes failure counts | Harness with/without DCCLISTEN | Failures only local; PRIVMSG flood of full log |
| S6 | Extension id + update URL | Default id `cgmpadejahkaggjpffnhaoiafbnicgpa`; ForceInstall update URL **`https://clients2.google.com/service/update2/crx`** for **both** Chrome and Edge policy trees | Config/example + tests | Missing default; different undocumented URLs without config |
| S7 | Secrets / blast radius | No domain passwords on IRC; machine account first; optional CredMan target `PriorityAirc/ExtensionAdmin` only; no secrets in DCC/intake | Redaction tests | Password in EXTENSION args or DCC log; invent CredMan target names |
| S8 | Auth = UPDATE | Same ops/half-ops gate as UPDATE; **`update=off` also refuses EXTENSION** | Cap matrix tests | EXTENSION works when update=off; arbitrary bob-* |

LOCKED.

## Shape

Primary: **service** (new Airc console verb + isolated worker).

LOCKED

## Stack

Default: Airc console `EXTENSION install` [-WhatIf] -> **detached worker** (PowerShell) -> **GroupPolicy** module (`New-GPO` / `Set-GPRegistryValue`) on GPO **`Priority-web-extension`** linked at **domain root** -> LDAP AD computer enum -> per-host **raw remote registry** (machine account, then CredMan **`PriorityAirc/ExtensionAdmin`**) -> best-effort remote `gpupdate /force` -> reverse DCC for log bytes. `-WhatIf` = read-only full plan (no writes).

ForceInstall entry shape: `cgmpadejahkaggjpffnhaoiafbnicgpa;https://clients2.google.com/service/update2/crx`

Why: Matches fleet remote-control wire, UPDATE isolation + UPDATE auth reuse, Chromium enterprise force-install.

Why-not: GPMC-COM-only; backup-modify-import as primary; IRC-thread GPO; separate ExtensionInstaller.exe; fallback-only-when-GPO-fails (holes after successful GPO would remain).

LOCKED

## Architecture

```
Operator/agent
 [optional] DCCLISTEN id=... host=... port=... token=...
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
 1) Find DC + New-GPO/Set-GPRegistryValue on GPO Priority-web-extension
 (link domain root); Chrome+Edge ForceInstall id+update2/crx
 2) ALWAYS then: LDAP enum computers -> fill holes via raw remote registry
 (machine account; CredMan PriorityAirc/ExtensionAdmin on access-denied)
 3) Best-effort gpupdate /force on reachable hosts
 4) Structured log; -WhatIf = full read-only plan, zero writes
 |
 v
Airc replies
 - short IRC summary + out id= seq= pages + DONE id= exit= (VISION S3 / FR #2570)
 - full log via reverse DCC TLS 1.2 when DCCLISTEN (FR #5003/#5008 send_offer_payload), else IRC CONT; including failures
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
- Default GPO name **`Priority-web-extension`**; create if missing, update if present; **link to domain root**
- Fallback **always after GPO** to fill holes (LDAP AD computers + local/registry)
- Per-host auth: machine account first; CredMan target **`PriorityAirc/ExtensionAdmin`** on access-denied
- Auth/cap: same as UPDATE; `update=off` blocks EXTENSION
- After GPO: trigger `gpupdate /force` on reachable hosts (best-effort, log failures)
- `-WhatIf`: **read-only full plan** - DC/GPO inspect + LDAP enum + list hole hosts; **no writes** (no GPO change, no registry, no gpupdate)
- Non-domain / workgroup hosts appearing in AD enum: **raw remote registry** ForceInstall only (**no LGPO.exe**); skip if unreachable
- Isolated worker; DCC log including failures
- Chrome + Edge

## UNKNOWN

- (none for MVP - operator MC cards closed 2026-10-31)

## Implementation slices

See GitHub issues #5290-#5295 (FR-A through FR-F implement slices).

## FR #5295 (capability slice)

Dedicated extension cap sits beside update. Client and workstation default extension=off. DONE exit=126 extension-disabled when cap-off. Parent S8 still holds: update=off refuses EXTENSION. Auth remains live +o/+h.
