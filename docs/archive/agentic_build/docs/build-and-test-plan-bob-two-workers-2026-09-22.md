<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/build-and-test-plan-bob-two-workers-2026-09-22.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Build and test plan: bob two persistent workers

**Date:** 2026-09-22  
**FR:** docs/feature-request-bob-two-persistent-workers-2026-09-22.md  
**Repo:** SimonBarnett/agentic_build

## Goals

1. Park + implement P0 so `bob-{machine}` can own a repo with two persistent workers (dev + MRB), webhook `working_on`, digest visible.
2. Keep existing one-shot loop working until the pair path is live (no break).

## Non-goals

- Human UAT stamp.
- Push/merge `main` from the implementer.
- Undo shop/fleet JOIN policy except as Simon already overrode (#107).

## Locked constants

| Name | Value |
|------|--------|
| Chair | `bob-{machine}` grok agent |
| Pair size | 2 workers per assigned repo |
| Idle stop | 5 minutes (U1 default) |
| Skills on spawn | build + IRC |
| Self-review | forbidden; other worker MRBs |
| Fuel | cursor-models while remaining > 0; never Other Models |

## Phase order

| Phase | Exit |
|-------|------|
| P0 | FR + this plan + issue; skill text for pair spawn + idle + webhook |
| P1 | Bob MUST start pair with IRC+build skills and direct JOIN IRC; persist; idle-stop |
| P2 | Implementer/MRB split + next-PR handoff |
| P3 | Worker `working_on` POST; digest reads it |
| P4 | Bob reports digest states (dev complete / MRB complete) to #bobiverse |
| P5 | Channel description = assigned repo name; update on repo change |
| P6 | Bob chair UAT via new UAT skill (not worker stamp) |
| P7 | Workers do own work; no nested agent invoke |
| P8 | Bob monitors in-flight; shop ping every 15 min; restart/intervene if stalled |
| P9 | Bob assigns MRB vs dev; any bobiverse agent idle > 20s |
| P10 | Bob checks outstanding tickets every 2 hours during business hours and assigns |
| P11 | Dynamic models: dev=less, MRB=medium, UAT=more |
| P12 | MRB merges dups, closes finished issues, merges PASS-nits PRs |
| P13 | Each bob webhooks identity + local grok remaining |
| P14 | Each bob reports account Cursor values; take the lesser of variance |
| P15 | Workers do not send to IRC channels; webhook only |
| P16 | Webhook real usage pools: remaining % + period start; 0 is 0; n/a only if unavailable |
| P17 | Workers use Cursor unless out of tokens, then local xAI |
| P18 | Bob decides local agent vs agent.com |
| P19 | Each Bob !bobiverse: webhook if Cursor or local xAI changed |
| P20 | bob-machine ops on own shop; Jeeves ops on #bobiverse |
| P21 | Control systray reflects proper Cursor metrics |

## Tests

| ID | Check |
|----|--------|
| T0 | `tools/Test-Pack.ps1` still green |
| T1 | Docs/skill mention pair, idle, webhook, no self-MRB |
| T2 | Spawn does not enqueue two jobs that both implement the same SHA |
| T3 | Digest/webhook test or documented POST path for workers |

## Definition of done (first ticket / P0–P1)

- [x] PR title includes the FR issue number
- [x] T0 green
- [x] Hostile MRB by the **other** worker; implementer does not merge
- [x] No UAT stamp

## Kickoff (`Start-BobBuild -Goal`)

Read `docs/feature-request-bob-two-persistent-workers-2026-09-22.md` and this plan.
Implement P0 then P1 on a branch. Open a PR. Never push main. Never merge.
Do not stamp UAT. Do not assign API keys. PR model composer-2.5. Never Other Models.
