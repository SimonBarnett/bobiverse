# Feature request: Airc NETWORK — customer-network diagnostic

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Decisions locked:** operator request 2026-10-31 (park-only)

Related: `airc/VISION.md`, DCC bulk FR #5003 / #5008 / upload FR #5194, remote-control verb model (`STATUS` / `UPDATE`), EXTENSION isolation pattern (`airc/docs/feature-request-airc-extension-priority-web-2026-10-31.md`).

## Objective

LOCKED: An authorized remote **`NETWORK`** (or `NETWORK diag`) on `{mid}_console` runs a **customer-network diagnostic** from the Airc box (which sits on that LAN): inventory of machines, **IP addresses**, and **OU / AD computer data**, in an **isolated** worker that cannot crash service `Airc`, and returns the structured **data + operation log** via reverse **DCC** when the caller offered `DCCLISTEN` (else IRC CONT pages), with a short IRC summary always.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | NETWORK verb | Authorized `NETWORK` / `NETWORK diag` accepted; unauthorized denied with UPDATE-class exit | Wire tests in `airc/tests/`; skills document verb | No verb; agents invent ad-hoc `cmd: nbtstat` floods |
| S2 | Machine inventory | Diagnostic lists domain (or configured) computers with hostname + at least one IP when DNS/ARP/LDAP resolves | Fixture/lab: `hosts[].name` and `hosts[].ips[]` present in payload | Empty inventory when AD/DNS has computers; invents hosts outside enum |
| S3 | OU / AD data | Each AD-backed host includes distinguishedName / OU path (or explicit `ou=unknown` when LDAP lacks it) | Payload schema + lab LDAP fixture | OU always blank on domain-joined console with LDAP rights |
| S4 | Isolation | Work runs in a **detached / child worker** — never LDAP/DNS/sweep loops on the IRC receive thread; worker faults must not stop service `Airc` | Fault-injection: worker throw → `Get-Service Airc` still Running; console still handles `STATUS` | Enum on message handler; service Stopped after bad NETWORK |
| S5 | DCC data + logs | Structured **data** (inventory) and **log** (steps, per-host resolve failures) via reverse **DCC** when `DCCLISTEN` offered for the job id; else IRC CONT; short IRC summary includes host/failure counts | Harness with/without `DCCLISTEN`; `DONE … via=dcc` + sha match | Full inventory only in PRIVMSG flood; failures only on console disk |
| S6 | Secrets / blast radius | No passwords on IRC; no domain creds in DCC body; machine/LDAP read with console rights only unless CredMan configured later | Redaction tests on sample log bytes | Password/token in NETWORK args or DCC payload |
| S7 | Auth | Same ops/half-ops gate as other privileged verbs (`STATUS` is lighter; prefer **UPDATE**-class auth for NETWORK) | Cap matrix tests | Arbitrary `bob-*` can NETWORK |

LOCKED.

## Shape

Primary: **service**

New Airc console verb + isolated worker; IRC/DCC wire surface only (no GUI product).

LOCKED

## Stack

Default: Airc console `NETWORK` / `NETWORK diag` → **detached worker** (PowerShell) → LDAP / AD computer enum (when domain) + DNS/local resolution for IPs + OU from `distinguishedName` → structured JSON (or line protocol) inventory + step log → reverse **DCC** for bulk bytes (FR #5003 path) with CONT fallback.

Why: Matches fleet remote-control wire and EXTENSION isolation/DCC pattern; Airc already sits on the customer LAN so agents outside the site can diagnose without AnyDesk UI.

Why-not: Long-running enum on the IRC thread; dumping multi-KB tables over PRIVMSG; requiring a separate NetworkDiag.exe install; inventing hosts from ARP alone without AD/DNS attribution.

LOCKED

## Architecture

```
Operator/agent
  [optional] DCCLISTEN id=<job> host=… port=… token=…
  PRIVMSG {mid}_console :id=<job> NETWORK diag
       |
       v
Airc service (live)
  - auth: UPDATE-class (+o/+h)
  - reply accepted / start job
  - spawn ISOLATED worker
       |
       v
NETWORK worker (isolated)
  1) Discover domain / workgroup context
  2) Enumerate computers (LDAP AD when available; document workgroup limits)
  3) Resolve IPs (DNS / existing adapters; best-effort)
  4) Attach OU / DN from LDAP when present
  5) Structured data + log (ok/fail per host/step)
       |
       v
Airc replies
  - short IRC summary (counts) + DONE exit=
  - full data+log via DCC (or CONT) including failures
```

LOCKED for Phase 0.

## Screens

Wire-only. HTML mocks under `airc/docs/mocks/` describe IRC summary / empty / error states for intake validation (not a GUI product).

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| NETWORK verb | Absent | `NETWORK` / `NETWORK diag` + UPDATE-class auth |
| Inventory | Ad-hoc shell (`Get-ADComputer`, `nslookup`) via `cmd:`/`ps` | First-class verb with schema |
| OU / IP | Manual LDAP/DNS | Packaged in one payload |
| Isolation | UPDATE / EXTENSION detached pattern | Same class for NETWORK |
| DCC | Shell bulk FR #5003; EXTENSION log FR-D | NETWORK job **data + log** via `DCCLISTEN` |

## LOCKED

- Repo `SimonBarnett/bobiverse`; product `airc/`
- Grammar MVP: `NETWORK` and/or `NETWORK diag` (no destructive write flags)
- Isolated worker; service must survive worker faults
- Payload includes machines, IPs, OU/DN (or explicit unknown)
- DCC when offered; CONT fallback; short IRC summary always
- No secrets on IRC or in DCC body
- Auth: UPDATE-class (+o/+h)
- Park-only this turn (no bob-job dispatch from intake seat)

## UNKNOWN

- Exact JSON vs NDJSON schema field names (freeze in FR-B implementation)
- Workgroup / non-domain console: ARP/NetBIOS-only inventory scope vs refuse with clear exit
- Whether CredMan domain-read account is in MVP or machine-account LDAP only
- Timeout / max host cap defaults for large OUs
- Whether `NETWORK status` (last job) is MVP or follow-up

## Implementation slices

1. **FR-A** — `NETWORK` verb + isolated worker scaffold (stub payload OK) — [#5298](https://github.com/SimonBarnett/bobiverse/issues/5298)
2. **FR-B** — Inventory collect: machines, IPs, OU/AD data — [#5299](https://github.com/SimonBarnett/bobiverse/issues/5299)
3. **FR-C** — DCC delivery of data + structured log (failures included) — [#5300](https://github.com/SimonBarnett/bobiverse/issues/5300) (implemented: `build_network_payload` / `deliver_network_payload`)
4. **FR-D** — Skills/docs (`bobiverse-airc-commands`, `airc-remote-control.md`) — [#5301](https://github.com/SimonBarnett/bobiverse/issues/5301)

Docs PR: [#5297](https://github.com/SimonBarnett/bobiverse/pull/5297).

## Out of scope (MVP)

- Mutating network config, firewall, or DNS
- Port scanning / vulnerability scanning as a product feature
- DCC upload to console (FR #5194)
- Replacing AnyDesk or Priority connectivity tooling
