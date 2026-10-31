# Feature request: Airc NETWORK — domain network diagnostic

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-145401`  
**Decisions:** operator MC cards 2026-10-31

Related: `airc/VISION.md`, DCC FR #5003 / #5008, STATUS framing, EXTENSION isolated-worker pattern.

## Objective

LOCKED: An authorized remote **`NETWORK diag`** on `{mid}_console` runs an **isolated** domain network diagnostic that inventories **AD LDAP computer objects** with **hostname, IPs, OU, reachability**, plus **ICMP ping and DNS** checks, and records **local** airc STATUS/VERSION on the console box — returning a structured result **via DCC** (CONT fallback) including failures — without crashing service `Airc`.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | NETWORK verb | Authorized `NETWORK diag` [optional `-WhatIf`] accepted; auth **same as STATUS** (ops/half-ops; allowed when `shell=off`); unauthorized → existing auth exits | Wire tests; skills | No verb; blocked by shell=off incorrectly |
| S2 | AD inventory | Worker enumerates AD computer objects via LDAP; each row includes hostname, resolved IP(s), OU distinguished name/path, reachability summary | Lab domain: DCC/JSON lists computers with OU + IPs | Invents hosts outside AD; missing OU; no IPs when DNS works |
| S3 | Ping + DNS | For each inventoried host (or bounded subset documented), record DNS resolve result and ICMP reachability; failures listed in log | Fixture/lab: known up/down hosts marked correctly | Silent skip of all probes; hangs IRC thread |
| S4 | Local console note | Result includes local airc service/STATUS/VERSION snapshot for the console box (no remote IRC port probes on peer hosts) | Log contains local `airc_ver` / Running; no mandatory TCP 6667 scans of AD PCs | Remote Ergo port scan required for DONE |
| S5 | Isolation | Detached/child worker (EXTENSION/UPDATE class); LDAP/ping loops never on IRC receive thread; worker fault → Airc still Running | Fault injection | Service Stopped after NETWORK |
| S6 | DCC data + logs | Full structured inventory + probe log via reverse DCC when `DCCLISTEN` offered, else CONT; short IRC summary + DONE; all failures in log | Harness with/without DCCLISTEN | Multi-KB PRIVMSG flood only; failures omitted |
| S7 | `-WhatIf` | Read-only full plan: may still LDAP enum + DNS (no destructive actions; NETWORK is read-only — WhatIf = same inventory without optional aggressive probes if any are added later). MVP: WhatIf ≡ diag (all read-only) or skips ICMP if operator policy prefers — **LOCKED MVP: WhatIf runs full read-only diag including ping/DNS** (ICMP is non-mutating) | Wire: WhatIf returns same schema, exit=0, no writes | WhatIf mutates AD/GPO |
| S8 | Secrets | No passwords on IRC/DCC; machine account LDAP; no secret OU data beyond DN names | Redaction | Creds in log |

LOCKED.

## Shape

Primary: **service** (console verb + isolated worker).

LOCKED

## Stack

Default: Airc `NETWORK diag` → detached PowerShell/Python worker → LDAP AD computers → DNS + ICMP → local STATUS/VERSION read → JSON/line log → DCCLISTEN path (FR #5003).

Why: Customer-network debug from inside; reuse EXTENSION LDAP + DCC patterns; STATUS-like auth for read-only.

Why-not: In-process IRC-thread scans; subnet invent without AD; remote IRC port scanning of every PC; separate NetworkDiag.exe product.

LOCKED

## Architecture

```
Operator/agent
  [optional] DCCLISTEN id=… …
  PRIVMSG {mid}_console :NETWORK diag [-WhatIf]
       |
       v
Airc service (live)
  - auth = STATUS (+o/+h); shell=off still allows NETWORK
  - spawn ISOLATED worker
       |
       v
NETWORK worker
  1) LDAP enum AD computers → hostname, OU, DNS→IPs
  2) ICMP + DNS probes; record failures
  3) Local airc Running + VERSION/STATUS fields
  4) Structured log → DCC or CONT
       |
       v
DONE id= exit= + short summary
```

LOCKED

## Screens

None.

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| NETWORK verb | Absent | New verb |
| AD inventory + OU + IPs | Absent (EXTENSION will add LDAP later; share helper) | Network diag inventory |
| Ping/DNS matrix | Absent | Probes in worker |
| Isolation + DCC | UPDATE/EXTENSION patterns | Apply to NETWORK |

## LOCKED

- Repo `SimonBarnett/bobiverse`; `airc/`
- Grammar: `NETWORK diag` optional `-WhatIf`
- Discovery: AD LDAP computers + DNS/IP resolve (not free subnet invent)
- Fields: hostname, IPs, OU, reachability; ping + DNS; local airc STATUS/VERSION only (no remote IRC ports)
- Auth: same as STATUS; allowed when shell=off
- Isolated detached worker; DCC log + failures (CONT fallback)
- Anti-omnibus slices

## UNKNOWN

- Max host / timeout / parallelism knobs (defaults TBD in implement FR-A)
- Exact JSON schema field names
- Whether to share LDAP helper module with EXTENSION FR #5292
- IPv6 inclusion vs IPv4-only MVP

## Implementation slices

See `drafts/backlog.md`.
