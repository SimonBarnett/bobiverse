# Feature request: Airc LEGION — remote install via network installer

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-150101`  
**Builds on:** FR #3991 `airc-network-installer.exe` (already laid in MSI at `<ai root>\airc\airc-network-installer.exe`)

## Objective

LOCKED: An authorized remote **`LEGION {target}`** on `{mid}_console` installs **airc** on one Windows **hostname or IP** by running the existing **`airc-network-installer`** (latest GitHub Release MSI, **`AIRC_PROFILE=client`**) inside an **isolated** worker, with CredMan **`PriorityAirc/LegionAdmin`**, returning **DCC** logs and failures (CONT fallback), without crashing service `Airc`. Optional **`-WhatIf`** dry-run.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | LEGION verb | `LEGION {target}` [optional `-WhatIf`] accepted; auth **same as UPDATE** (`update=off` blocks); unauthorized → existing exits | Wire tests | No verb; agents run installer by hand only |
| S2 | Uses network installer | Worker invokes laid-in / packaged `airc-network-installer` (FR #3991) for that single target — latest Release airc MSI, profile **client** — not a new parallel installer | Log shows installer invocation; MSI from bobiverse Releases | Reimplements msiexec from scratch; foreign MSI URL |
| S3 | Target installed | Happy path: target ends with service **Airc** Running (or installer-documented success); `-WhatIf` makes no remote changes | Lab VM; WhatIf → dry-run flags | WhatIf writes; success claimed without installer ok |
| S4 | Isolation | Detached worker only; never run network-installer/msiexec/PsExec on IRC receive thread; worker fault → Airc still Running | Fault injection | Service Stopped after LEGION |
| S5 | DCC logs | Full installer log + summary via DCC when `DCCLISTEN` offered, else CONT; failures included; short IRC + DONE | Harness | PRIVMSG-only multi-MB log; failures omitted |
| S6 | Secrets | CredMan `PriorityAirc/LegionAdmin` only; no password on IRC/DCC/intake | Redaction | Password in LEGION args |
| S7 | Single target | One hostname/IP per command; refuse empty/ambiguous TARGET | Parse tests | OU/list expansion without new FR |

LOCKED.

## Shape

Primary: **service** (console verb orchestrating existing network-installer exe/module).

LOCKED

## Stack

Default: Airc `LEGION {target}` → detached worker → `airc-network-installer` (`--hosts {target} --profile client`, latest MSI download as today) with CredMan `PriorityAirc/LegionAdmin` mapped to installer username/password prompts/env as documented — never echo password → DCC log dir / summary.

Why: FR #3991 already compiles and ships the installer; LEGION makes it a first-class remote verb like UPDATE/NETWORK.

Why-not: New install engine; CIDR/AD blast from LEGION MVP (installer still supports those offline); STATUS-level open auth.

LOCKED

## Architecture

```
Operator
  [optional] DCCLISTEN …
  PRIVMSG {mid}_console :LEGION {hostname|ip} [-WhatIf]
       |
       v
Airc service
  - auth = UPDATE; update=off refuse
  - spawn ISOLATED worker
       |
       v
LEGION worker
  - resolve CredMan PriorityAirc/LegionAdmin
  - run airc-network-installer for single --hosts TARGET
    profile=client, latest MSI (or --dry-run for -WhatIf)
  - collect log-dir / summary → DCC or CONT
       |
       v
DONE id= exit=
```

LOCKED

## Screens

None.

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| `airc-network-installer.exe` | Shipped in MSI (FR #3991); CLI/PsExec/AD/CIDR | Not a console verb |
| LEGION | Absent | Verb + isolation + DCC + CredMan wire |
| Remote install from IRC | Manual drop/run installer | First-class LEGION |

## LOCKED

- Grammar: `LEGION {target}` optional `-WhatIf`; target = one hostname or IP
- Reuse FR #3991 network installer; profile **client**; **latest** Release MSI
- Auth = UPDATE; `update=off` blocks LEGION
- CredMan: `PriorityAirc/LegionAdmin`
- Isolated worker; DCC logs + failures
- Anti-omnibus slices

## UNKNOWN

- Exact argv mapping CredMan → installer (`-u` + env vs helper wrapper)
- Whether laid-in `airc-network-installer.exe` must be preferred over `python -m airc_network_installer`
- Per-host timeout default for single-target LEGION (installer default 900s OK?)
- Force reinstall flag out of MVP (installer has `--force`)

## Implementation slices

See `drafts/backlog.md`.
