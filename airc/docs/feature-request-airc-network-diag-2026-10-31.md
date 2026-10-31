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
| S2 | AD inventory | Worker enumerates AD computers via **shared LDAP helper** (with EXTENSION #5292); each row: `hostname`, `ips[]` (**IPv4/A**), `ou`; **reachability is derived** (`reachable = any(ping_ok)` across that host's IPv4s; no extra field); cap **500** hosts with `truncated` meta when over | Lab: DCC/JSON rows with OU + IPv4; shared helper used | Invents non-AD hosts; unbounded enum; IPv6 required for DONE |
| S3 | Ping + DNS | Per host (≤500): DNS + ICMP with **1s** timeouts, **32** parallel; fields `dns_ok`, `ping_ok`, `error`; failures in log | Lab: up/down hosts; parallelism bounded | Silent skip; IRC-thread hang; no timeout |
| S4 | Local console note | Result includes local airc service/STATUS/VERSION snapshot for the console box (no remote IRC port probes on peer hosts) | Log contains local `airc_ver` / Running; no mandatory TCP 6667 scans of AD PCs | Remote Ergo port scan required for DONE |
| S5 | Isolation | Detached/child worker (EXTENSION/UPDATE class); LDAP/ping loops never on IRC receive thread; worker fault → Airc still Running | Fault injection | Service Stopped after NETWORK |
| S6 | DCC data + logs | Full structured inventory + probe log via reverse DCC when `DCCLISTEN` is offered **with the same job `id=` as `NETWORK diag`**. DCC connect/handshake fail → fall back to CONT pages and `DONE ... via=irc reason=dcc-fail` (same as FR #5003). Success DONE includes `via=dcc` transfer meta. No DCCLISTEN → CONT only. Short IRC summary + DONE; all failures in log | Harness with/without DCCLISTEN | Multi-KB PRIVMSG flood only; failures omitted |
| S7 | `-WhatIf` | Read-only full plan: may still LDAP enum + DNS (no destructive actions; NETWORK is read-only — WhatIf = same inventory without optional aggressive probes if any are added later). MVP: WhatIf ≡ diag (all read-only) or skips ICMP if operator policy prefers — **LOCKED MVP: WhatIf runs full read-only diag including ping/DNS** (ICMP is non-mutating) | Wire: WhatIf returns same schema, exit=0, no writes | WhatIf mutates AD/GPO |
| S8 | Secrets | No passwords on IRC/DCC; machine account LDAP; no secret OU data beyond DN names | Redaction | Creds in log |

LOCKED.

## Shape

Primary: **service** (console verb + isolated worker).

LOCKED

## Stack

Default: Airc `NETWORK diag` → detached worker → **shared** LDAP/AD helper → DNS (A/IPv4) + ICMP (1s, 32-wide, max 500) → local STATUS/VERSION → snake_case JSON (`hostname`, `ips[]`, `ou`, `dns_ok`, `ping_ok`, `error` + meta) → DCCLISTEN (FR #5003).

Why: Customer-network debug from inside; shared LDAP with EXTENSION; STATUS-like auth; bounded probes.

Why-not: In-process IRC-thread scans; subnet invent without AD; remote IRC port scanning of every PC; separate NetworkDiag.exe product.

LOCKED

## Architecture

```
Operator/agent
  [optional] DCCLISTEN id=<job> …
  PRIVMSG {mid}_console :NETWORK diag [-WhatIf]  (same id=<job>)
       |
       v
Airc service (live)
  - auth = same STATUS path (channel +o/+h/+a/+q); shell=off still allows NETWORK
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
- Defaults: **max 500 hosts**; **1s DNS** + **1s ping** timeouts; **32** parallel probes; overflow hosts listed as `truncated`
- Result schema (snake_case): per host `hostname`, `ips[]`, `ou`, `dns_ok`, `ping_ok`, `error`; meta `machine`, `airc_ver`, `airc_running`, `truncated`
- **Shared** airc LDAP/AD helper module with EXTENSION fill-holes (#5292)
- **IPv4-only MVP** (A records + IPv4 ping); AAAA/IPv6 follow-on
- Anti-omnibus slices

## UNKNOWN

- (none for MVP — operator MC cards closed 2026-10-31)

## Implementation slices

Anti-omnibus: one issue at a time.

- FR-A verb + isolated worker: SimonBarnett/bobiverse#5302
- FR-B AD LDAP inventory: #5303
- FR-C ping/DNS + local STATUS: #5304
- FR-D DCC result log: #5305
- FR-E skills/docs: #5306
