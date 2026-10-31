# Feature request: Airc LEGION  -  remote install via network installer

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-150101`  
**Builds on:** FR #3991 `airc_network_installer` module / tooling (logic reused in-service; standalone exe may remain for offline use)

**Decisions locked:** operator MC cards 2026-10-31

## Objective

LOCKED: An authorized remote **`LEGION {target}`** on `{mid}_console` installs **airc** on one Windows **hostname or IP** by having the **Airc service spawn a new isolated worker process** that **imports the `airc_network_installer` module** (FR #3991 logic  -  latest GitHub Release MSI, **`AIRC_PROFILE=client`**, **no `--force`** in MVP)  -  **not** as a separate operator-facing product exe  -  with CredMan **`PriorityAirc/LegionAdmin`** passed via a **wrapper** (`-u` + password over secure env/channel the installer accepts; never on IRC), returning **DCC** logs and failures (CONT fallback), without crashing service `Airc`. Optional **`-WhatIf`** → installer dry-run. Per-host timeout **900s** (installer default).

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | LEGION verb | `LEGION {target}` [optional `-WhatIf`] accepted; auth **same as UPDATE** (`update=off` blocks); unauthorized → existing exits | Wire tests | No verb; agents run standalone installer by hand only |
| S2 | In-service installer logic | Service-owned **new worker instance** imports **`airc_network_installer`** for that single target  -  latest Release airc MSI, profile **client**  -  **not** shelling out to a separate product `airc-network-installer.exe` as the LEGION path | Log shows module worker; MSI from bobiverse Releases | LEGION requires operator to launch standalone exe; foreign MSI URL; reimplements msiexec from scratch |
| S3 | Target installed | Happy path: target ends with service **Airc** Running (or installer-documented success); `-WhatIf` makes no remote changes; **never** pass `--force` in MVP | Lab VM; WhatIf dry-run | WhatIf writes; `--force` used; success without installer ok |
| S4 | Isolation | New detached worker process only; never run install/PsExec on IRC receive thread; worker fault → Airc still Running | Fault injection | Service Stopped after LEGION |
| S5 | DCC logs | Full installer log + summary via DCC when `DCCLISTEN` offered, else CONT; failures included; short IRC + DONE | Harness | PRIVMSG-only multi-MB log; failures omitted |
| S6 | Secrets | CredMan `PriorityAirc/LegionAdmin`; wrapper passes `-u` + password via **secure env/channel** (never IRC; prefer never cleartext argv); redaction tests | Grep/process-list policy in tests | Password in LEGION IRC line or DCC log |
| S7 | Single target | One hostname/IP per command; refuse empty/ambiguous TARGET; timeout **900s** | Parse + timeout tests | OU/list expansion; unbounded hang |

LOCKED.

## Shape

Primary: **service**

LEGION is part of Airc; starts a new isolated worker instance importing the network-installer module.

LOCKED

## Stack

Default: Airc `LEGION {target}` → **new isolated worker process** → import **`airc_network_installer`** (single host, profile client, latest MSI, timeout 900, no `--force`; `-WhatIf` → dry-run) → CredMan wrapper (`PriorityAirc/LegionAdmin` → `-u` + secure password channel) → DCC log/summary.

Why: FR #3991 logic already exists; LEGION makes it a first-class **service** capability like UPDATE/NETWORK without a peer product exe path.

Why-not: Operator-launched `airc-network-installer.exe` as the LEGION implementation; new install engine; CIDR/AD blast from LEGION MVP; STATUS-level open auth; always `--force`.

LOCKED

## Architecture

```
Operator
  [optional] DCCLISTEN …
  PRIVMSG {mid}_console :LEGION {hostname|ip} [-WhatIf]
       |
       v
Airc service (live console)
  - auth = UPDATE; update=off refuse
  - spawn NEW ISOLATED worker PROCESS (service-owned)
       |
       v
LEGION worker instance
  - CredMan PriorityAirc/LegionAdmin → wrapper (-u + secure env/channel)
  - import airc_network_installer for single TARGET
    profile=client, latest MSI, timeout=900, no --force
    (-WhatIf → dry-run)
  - collect logs/summary → DCC or CONT
       |
       v
DONE id= exit=
```

LOCKED

## Screens

Wire-only. HTML mocks under airc/docs/mocks/legion/ (home / empty / error) for intake validation (not a GUI product).


## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| `airc_network_installer` / exe | FR #3991 module + frozen exe in MSI | Not wired as console LEGION worker |
| LEGION | Absent | Verb + service-owned worker instance + CredMan wrapper + DCC |
| Remote install from IRC | Manual run of network installer | First-class LEGION |

## LOCKED

- Grammar: `LEGION {target}` optional `-WhatIf`; target = one hostname or IP
- **Part of Airc service:** new isolated worker process **imports `airc_network_installer` module** (no separate product exe as the LEGION path)
- Profile **client**; **latest** Release MSI; timeout **900s**; **no `--force`** in MVP
- Auth = UPDATE; `update=off` blocks LEGION
- CredMan: `PriorityAirc/LegionAdmin`; wrapper → `-u` + secure env/channel (not IRC)
- DCC logs + failures
- Anti-omnibus slices

## UNKNOWN

- (none for MVP  -  operator MC cards closed 2026-10-31)

## Implementation slices

1. **FR-A** - LEGION verb + isolated worker scaffold - https://github.com/SimonBarnett/bobiverse/issues/5308
2. **FR-B** - invoke airc_network_installer for one target - https://github.com/SimonBarnett/bobiverse/issues/5309 (module import, client profile, WhatIf=dry-run)
3. **FR-C** - CredMan PriorityAirc/LegionAdmin wrapper - https://github.com/SimonBarnett/bobiverse/issues/5310 (fail closed ``credman-missing``; secret never on IRC)
4. **FR-D** - DCC install logs including failures - https://github.com/SimonBarnett/bobiverse/issues/5311
5. **FR-E** - Skills/docs - https://github.com/SimonBarnett/bobiverse/issues/5312

Docs PR: https://github.com/SimonBarnett/bobiverse/pull/5313 . Living slices stay open (Refs only).
#5308 #5309 #5310 #5311 #5312

