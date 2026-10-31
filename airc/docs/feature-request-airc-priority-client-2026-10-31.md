# Feature request: Built-in Priority Client for Airc

**Repo:** `SimonBarnett/bobiverse`  
**Product path:** `airc/`  
**Date:** 2026-10-31  
**Plan folder:** `bob/plan/work/plan-20261031-142606`  
**Prior art:** `M:\ai\Airc-Priority` (samples under plan `prior-art/`)

Related product vision: `airc/VISION.md` (FR #4158). Fleet umbrella: `common/docs/vision.md`.

## Objective

LOCKED: On any airc box that can reach a Priority web host, an authorized operator or agent drives Priority through **built-in Airc `PRIORITY` verbs** (Web SDK), with CredMan secrets and measurable prepare/form-walk success, without dropping ad-hoc Priority client packs under `drop\` or inventing a separate Priority `.exe`.

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | In-service client | Priority capability ships inside Airc install/service path (no separate Priority product exe; no agent-authored one-off client required for MVP ops) | MSI/layout includes Priority module under `airc/`; `Get-Service Airc` Running; verb help/STATUS advertises Priority; freeze/`airc.exe` path documents in-process or service-owned worker | Agents still told to copy `M:\ai\Airc-Priority` packs; a standalone `PriorityClient.exe` (or peer product) is the only path |
| S2 | Connect | `PRIORITY connect` (or equivalent) authenticates to an allowlisted instance using CredMan and returns machine-readable ok + company/url identity | Integration test or live probe on a DEV instance; CredMan target documented; IRC transcript has no password | Password on IRC/logs; connect without CredMan; invent URL/company not on allowlist |
| S3 | Form walk | Authorized verb sequence can `formStart` / subform / getRows (read path) and return structured JSON + `DONE id= exit=` | Automated test against recorded fixture or DEV allowlist form; framing matches FR #75 / Invoke-AircRemote | Agents must PUT custom `.mjs` clients for a basic walk; DONE missing/wrong |
| S4 | Named procedure prep | `PRIORITY prepare` (ENAME) uses EXEC → `REPPREPDIRECT2` and reports success only when SDK `ok=true` **and** `EXECPREPLOCK.UPD='N'` **and** `.prp` mtime advanced | Port gates from Airc-Priority prepare / `priority-procedure-prep` skill; SQL+file evidence in result JSON | Success claimed on toast alone; SQL flip `UPD='N'` without prep; form-prep path used for TYPE=P |
| S5 | Skills | `bobiverse-airc` + `bobiverse-airc-commands` (and related airc client skills) document Priority verbs, CredMan, allowlist, and hard gates | Skill files on tip; agent can follow skill without external NAS pack | Skills omit Priority; still point only at one-off drop clients |
| S6 | Secrets CAST IRON | No Priority password in IRC, intake, harvest, git, or logs | Grep/redaction tests; CredMan-only path | Cleartext password in any of those channels |

LOCKED. Customer Day Works Playwright packs are **out of MVP** (follow-on FR-H).

## Shape

Primary: **service**

Hybrid note: Product surface remains the **Airc** Windows service (`{mid}_console`). Priority is an **in-service capability** exposed as IRC console verbs. `Invoke-AircRemote.ps1` may gain Priority wrappers (delivery helper, not a second product).

LOCKED

## Stack

Default: Extend bobiverse `airc/` console (Python `airc_console` / frozen `airc.exe` + NSSM `Airc`) with `PRIORITY` verb routing; host `priority-web-sdk` (Node) as a **service-owned** worker packaged under the airc tree (or equivalent in-process bridge). CredMan for web passwords. Optional `sqlcmd` on-box for EXECPREPLOCK / `.prp` gates.

Why: Matches live airc remote-control wire (`DONE id= exit=`), fleet MSI distribution, and proven Web SDK packs.

Why-not: Separate Priority product exe; per-agent `drop\` clients; Playwright-first MVP; password files as default; inventing instance URLs in skills.

LOCKED (UNKNOWN: exact Node embed vs sidecar under service ACL — must remain service-owned).

## Architecture

```
Agent / operator (driving box)
  -> Invoke-AircRemote  OR  bob outbox PRIVMSG
       -> {mid}_console   PRIORITY <subcmd> ...
            -> Airc service (NSSM)
                 -> Priority Client module (in-service)
                      -> CredMan (web user password)
                      -> priority-web-sdk -> Priority HTTPS (allowlisted URL)
                      -> optional sqlcmd (EXECPREPLOCK + prep\.prp gates)
            <- out/err seq=  JSON results
            <- DONE id= exit=

Config (no secrets in git):
  allowlisted instances (url, company, user, credentialTarget, sql/prep paths)
```

Trust:

- IRC never carries Priority passwords.
- Instance allowlist required; refuse inventing `webBaseUrl` / company / SQL.
- Prepare success = SDK ok + UPD=N + `.prp` mtime advanced (never SQL-fake).
- Hotpatch/restart **Airc** only; never Ergo / BobIrcd.
- Client MSI allow-list must keep Priority module files when client profile needs them.

LOCKED for Phase 0 boundaries; verb grammar UNKNOWN until implement slices.

## Screens

No TipForm/HTML UI. Mocks out of scope (same as `airc/VISION.md`).

## Gap vs current tree

| Area | Today | Gap |
|------|-------|-----|
| Console verbs | STATUS, shell, PUT/RUN/GET, UPDATE, DCC, … | No `PRIORITY` verbs |
| Priority SDK | Not in bobiverse airc layout | Packaged Web SDK client owned by service |
| Agent practice | Copy/adapt packs from NAS / fomprep into `drop\` | Skills teach one-off clients |
| Creds | Ergo/NickServ patterns; Priority CredMan not wired | CredMan targets + allowlist config |
| Skills | `bobiverse-airc`, `bobiverse-airc-commands` | No Priority usage section |
| Tests | Rich `airc/tests` for shell/DCC/auth | No Priority connect/walk/prepare tests |

## LOCKED

- Repo `SimonBarnett/bobiverse`; product `airc/`; service `Airc`
- Web SDK first; IRC `PRIORITY` verbs; CredMan only
- MVP = connect + form walk + named procedure prep
- Part of Airc service — not a separate Priority product executable
- Prepare gates: ok + UPD=N + `.prp` mtime
- Airc skills must document Priority Client usage
- Anti-omnibus: many small Goal/Deliverables/Testable issues

## UNKNOWN

- Exact verb grammar
- Node worker embed mechanics (frozen exe vs files beside exe under service ACL)
- Client-profile MSI default vs opt-in for Priority module
- SQL gate required always vs fail-closed when sqlcmd missing
- Vendor vs reference relationship to `SimonBarnett/agentic_fomprep`
- Browser/Playwright Priority path (follow-on FR-H, SimonBarnett/bobiverse#5289; see `feature-request-airc-priority-playwright-2026-10-31.md`)
- Allowlist file path/schema under `<ai root>\airc\config\`

## Implementation slices

Anti-omnibus: file **one** small GitHub issue at a time.

- FR-A (schema + CredMan allowlist): SimonBarnett/bobiverse#5275
- FR-H (Playwright follow-on, out of MVP): SimonBarnett/bobiverse#5289 (`feature-request-airc-priority-playwright-2026-10-31.md`)
- Other slices: filed as separate issues (do not invent a repo `drafts/backlog.md`)
