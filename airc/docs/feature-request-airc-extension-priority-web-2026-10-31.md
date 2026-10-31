# Feature request: Airc EXTENSION — Priority web force-install (GPO + registry fallback)

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-143743`

Related: `airc/VISION.md`, DCC bulk FR #5003 / #5008, remote-control verb model (STATUS / UPDATE).

## Objective

LOCKED: An authorized remote **`EXTENSION`** command on `{mid}_console` force-installs the Priority web extension (`cgmpadejahkaggjpffnhaoiafbnicgpa`) for **Chrome and Edge** across the customer domain — happy path via **DC + GPO**, with **LDAP AD computer enum + per-host registry / local policy** fallbacks when GPO is unavailable — while the install worker runs **isolated** from the Airc service process and returns a **DCC** (or CONT fallback) log including every failure.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | EXTENSION verb | Authorized `EXTENSION` (grammar TBD) is accepted like STATUS/UPDATE; unauthorized → existing auth exits | Wire tests; skills document verb | No verb; agents hand-edit GPO only |
| S2 | GPO happy path | When a DC is reachable and caller has rights, worker finds DC and adds ForceInstall for extension id on **Chrome + Edge** domain policy so domain machines receive the extension | Lab/domain test: GPO/ExtensionInstallForcelist (or ADMX equivalent) contains `cgmpadejahkaggjpffnhaoiafbnicgpa` + documented update URL for both products | DC reachable but only one browser; silent no-op; wrong OU with no coverage |
| S3 | Registry / local-policy fallback | When DC/GPO unavailable or GPO apply fails, enumerate **AD computer objects (LDAP)** and apply local machine policy / registry ForceInstall on each **reachable** networked host for Chrome + Edge | Test with DC down or deny-GPO: reachable hosts get registry keys; unreachable hosts listed as failures in log | Fallback does nothing; only console box fixed; invents hosts outside AD |
| S4 | Isolation | EXTENSION work runs in a **detached / child worker** (or equivalent job) — never AD/GPO/registry loops on the IRC receive thread; worker faults must not crash or stop service `Airc` | Fault-injection: worker exception → service still Running + DONE/err; no unhandled exception killing console | GPO code in-process on message handler; service Stopped after bad EXTENSION |
| S5 | DCC log + failures | Operation writes a structured log (hosts attempted, GPO vs fallback, per-host ok/fail); delivered via reverse **DCC** when caller offered `DCCLISTEN` (FR #5003), else IRC CONT; **all failures** appear in that log and short IRC summary | Harness: DCCLISTEN + EXTENSION → via=dcc body lists failures; without DCCLISTEN → CONT pages include failures | Failures only in local files with empty IRC; multi-KB log floods PRIVMSG only |
| S6 | Extension id LOCKED | Default / primary id is `cgmpadejahkaggjpffnhaoiafbnicgpa` (Priority web); optional override only if allowlisted in config | Config/example + tests pin default id | Random ids without allowlist; missing default |
| S7 | Secrets / blast radius | No domain admin passwords on IRC; use existing machine identity / CredMan / run-as policy documented; no secrets in DCC/intake | Redaction tests | Password in EXTENSION args or DCC log |

LOCKED.

## Shape

Primary: **service** (new Airc console verb + isolated worker).

LOCKED

## Stack

Default: Airc console verb dispatch (Python) → **detached worker** (PowerShell preferred for GPO/AD/registry) → Group Policy / LGPO / registry `ExtensionInstallForcelist` for Chrome (`SOFTWARE\Policies\Google\Chrome\...`) and Edge (`SOFTWARE\Policies\Microsoft\Edge\...`) → LDAP AD computer enum for fallback → existing reverse DCC for log bytes.

Why: Matches fleet remote-control wire, UPDATE-style isolation precedent (FR #77 detached Apply), and Chromium enterprise force-install.

Why-not: Editing GPO inside the live IRC thread; shipping a separate ExtensionInstaller.exe product; per-agent one-off scripts; IRC-only multi-MB logs.

LOCKED (UNKNOWN: exact update URL string(s) for Chrome vs Edge store/enterprise; whether to use LGPO.exe vs raw registry; domain join required on console).

## Architecture

```
Operator/agent
  [optional] DCCLISTEN id=… host=… port=… token=…
  PRIVMSG {mid}_console :EXTENSION …
       |
       v
Airc service (live)
  - auth (+o/+h)
  - reply accepted / start job (DONE framing)
  - spawn ISOLATED worker (scheduled task / WMI / job proc)
  - never run DC/GPO/LDAP loops on IRC thread
       |
       v
EXTENSION worker (isolated)
  1) Try find DC + edit GPO ForceInstall (Chrome+Edge, id cgmpadejahkaggjpffnhaoiafbnicgpa)
  2) Else / also gaps: LDAP enum computers → per-host registry/local policy ForceInstall
  3) Build structured log (ok/fail per step/host)
       |
       v
Airc replies
  - short IRC summary + DONE exit=
  - full log via DCC (or CONT fallback) including failures
```

Trust: IRC control plane; DCC for bulk log; domain rights required for GPO/remote registry; fail closed without inventing DCs; hotpatch restarts Airc only — worker isolation means a hung GPMC must not take down the console.

LOCKED for Phase 0.

## Screens

None. Mocks out of scope.

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| EXTENSION verb | Absent | New verb + auth/capability |
| GPO / extension force-install | Absent in airc | DC discovery + Chrome/Edge ForceInstall |
| Per-host fallback | Absent | LDAP computer enum + registry/local policy |
| Isolation | UPDATE uses detached Apply | Same class of isolation for EXTENSION |
| DCC | Shell/bulk output FR #5003 | Wire EXTENSION job log through DCCLISTEN path |
| Extension id | Not in product | Pin `cgmpadejahkaggjpffnhaoiafbnicgpa` |

## LOCKED

- Repo `SimonBarnett/bobiverse`; product `airc/`
- Verb `EXTENSION`; default extension id `cgmpadejahkaggjpffnhaoiafbnicgpa`
- Chrome + Edge
- Happy path DC+GPO; fallback AD LDAP computers + local/registry ForceInstall
- Isolated worker (service must not die)
- DCC log including failures (CONT fallback)
- Anti-omnibus small issues

## UNKNOWN

- Exact verb grammar (`EXTENSION install`, flags for `-WhatIf`, browser filter)
- Chrome/Edge update URL(s) for ForceInstall list entries
- GPO edit mechanism (GPMC COM, `New-GPO`/`Set-GPRegistryValue`, backup-modify-import)
- Whether fallback runs only when GPO fails or also fills holes after GPO
- Remote registry auth (LocalSystem vs CredMan domain account)
- Capability flag (`jobs` / new `extension=` cap) for client profile
- gpupdate / wait policy after GPO change

## Implementation slices

See `drafts/backlog.md`.
