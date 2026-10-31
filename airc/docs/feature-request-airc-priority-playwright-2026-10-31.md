# Feature request: Airc Priority Playwright / browser path (FR-H follow-on)

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Issue:** SimonBarnett/bobiverse#5289  
**Parent:** `feature-request-airc-priority-client-2026-10-31.md` (UNKNOWN / FR-H)

Related: `airc/VISION.md`, isolated workers CAST IRON, CredMan FR #5275.

## Objective

LOCKED: Optional **browser / Playwright** Priority automation (screen and UAT-style drives) is a **follow-on** only. It **must not block** parent Success **S1-S6** (Web SDK MVP: in-service client, connect, form walk, prepare, skills, secrets). When implemented later, the path is **airc-owned** (service tree / MSI), never per-agent `drop\` packs or a standalone Priority browser exe.

## Success (follow-on; not MVP)

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| H1 | Parked | This note exists; parent cites #5289; S1-S6 stay Web SDK first | Doc tests `test_fr5289_*` | Playwright treated as MVP gate |
| H2 | Ownership | Later impl lives under `airc/` (service-owned worker), same allowlist + CredMan as Web SDK | Layout / pack tests when coded | Agents told to copy NAS Day Works packs |
| H3 | Secrets | No Priority password on IRC, intake, or Playwright traces committed to git | Redaction tests | Cleartext password in traces or skills |
| H4 | Isolation | Browser child is a service-owned process, not `PriorityClient.exe` | Isolated-workers rule | Peer product binary |

LOCKED. Do not implement H2-H4 in this FR. Design only.

## Shape

Primary: service

Hybrid note: same Airc console surface; Playwright is an optional later worker, not a second product.

LOCKED

## Stack

Default (later): Airc Priority module starts an in-tree Playwright worker against allowlisted URLs using CredMan. MVP remains Node `priority-web-sdk`.

Why: Screen/UAT drives need a browser. Why-not: Playwright-first MVP; per-agent packs.

LOCKED for this park. Implementation UNKNOWN until S1-S6 are green.

## Architecture

```
Later (not this FR):
  PRIORITY browser ...  -> airc-owned Playwright worker
       -> CredMan + allowlist (same as Web SDK)
       -> screens / UAT evidence
MVP now:
  PRIORITY connect / form / prepare -> Web SDK only
```

Trust: no secrets on IRC; hotpatch Airc only; never Ergo / BobIrcd.

## Screens

None in this park. Mocks out of scope.

## Out of scope

MVP connect, form walk, and prepare Web SDK verbs (other FRs). Customer Day Works Playwright packs stay reference-only, not the deploy path.

## UNKNOWN

- Verb grammar for a later browser slice
- Headless vs headed; trace retention
- Whether Playwright ships in fleet MSI or opt-in client profile
