# Vision: jeeves (chair)

Product folder: `jeeves/` in `SimonBarnett/bobiverse`. Fleet umbrella: `common/docs/vision.md`.
This file is the **jeeves-product** vision for MRB/UAT vision-first judgement (FR #5090; bob parity FR #1615; airc parity FR #4158).

## Objective

The Ergo host runs a maintained **ircJeeves** chair so fleet shops get FR/MRB/UAT offers on `#{machine}` without token spend, secret leakage, or stranded queues after seat recycle / GIVEUP / needs_human.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | Chair present | `ircJeeves` Running; nick `Jeeves` on `#bobiverse` + shop channels | `Get-Service ircJeeves`; chair log JOIN / cmd-trace | Service stopped or shops silent |
| S2 | Auto-offer feeds idle seats | `!bored` / done-offer / idle feed hand the next in-focus unaccepted row when gates allow | `offer_focus_top` / `jeeves/tests` chair focus; live `!status` unaccepted > 0 with idle seats | Idle seats hear `nothing queued` while ungated unaccepted rows exist |
| S3 | Give-up is exact-seat | GIVEUP/NACK `giveup_seats` + per-seat `cooldown_until` match the canonical seat nick only; a recycled fresh nick on the same machine can be auto-offered a non-`needs_human` row the dead predecessor gave up (same as `!assign`) | FR #5088; `test_fr5088_recycle_giveup_exact_nick.py`; `nick_in_giveup_seats` does not call `nick_inherits_dead_seat` | Recycled nick blocked on `!bored` solely because a dead same-machine nick is in `giveup_seats` |
| S4 | needs_human global auto-offer block | Once `needs_human` is stamped, auto-offer blocks every seat; only explicit `!assign` may hand the row out | FR #4336; `row_needs_human`; `test_fr4336_needs_human_recycle.py` | Auto-offer loops recycled nicks past `needs_human`; or other seats never blocked after stamp |
| S5 | CAST IRON harvest | Every gap/skill filed same turn via intake | `Report-BobiverseIntakeIssue.ps1`; jeeves skills / AGENTS lead with harvest rule | Findings left unfiled |

LOCKED

## Shape

Primary (one): service

Hybrid note: Windows service **ircJeeves** (optional frozen `jeeves.exe`) is the product core; BobCallback webhooks (:7700) and monitor scripts are chair companions (not a website). Ergo **BobIrcd** is a separate service on the same host.

LOCKED

## Stack

Default: Python `gitclaim` / chair agent (`irc_agent` chair mode), PowerShell install/start, NSSM `ircJeeves`, WiX jeeves MSI, private Ergo `irc.ntsa.uk`, IIS webhook front for `/bob/v1/*`.

Why: Matches live fleet install trees under `<ai root>\jeeves` and the composed flat runtime.

Why-not: LLM chair or public Libera --- shops, digests, and intake are Ergo + deterministic Jeeves.

LOCKED

## Architecture

```
Workers (#{machine})
  !bored / ACK / DONE / NACK / GIVEUP
       |
       v
ircJeeves (chair)
  ├─ nick Jeeves; +o on #bobiverse; silent assign on shops
  ├─ queue.json (unaccepted / accepted / done) + seat-ledger
  ├─ offer_focus_top / assign_row / gitclaim gates
  │    ├─ optional fuel-chain (FR #5317; each stage off by default; never load-bearing)
  │    ├─ focus / ignore / require_machine
  │    ├─ exact-seat giveup_seats + cooldown (FR #5088)
  │    ├─ needs_human global auto-offer block (FR #4336); !assign may still hand out
  │    ├─ MRB self-exclusion exact seat (FR #2604 / #4606)
  │    └─ UAT dead-author inherit still uses nick_inherits_dead_seat (FR #4336)
  ├─ !register / !recycle / !resync / !status / !assign (ops matrix)
  └─ never touch Ergo config as hotpatch of ircJeeves alone

BobCallback (:7700)
  └─ /bob/v1/git|intake|report|digest|jira  (IIS TLS)

MONITORING agent (jeeves CWD)
  └─ Invoke-JeevesMonitorCheck* --- report via intake; never act as chair
```

Trust: no secrets in filings/logs; GitHub token / DPAPI / NickServ stay in chair home. Hotpatch restarts **ircJeeves** only; never touch Ergo / `BobIrcd`. `!recycle jeeves` restarts ircJeeves only.

LOCKED

## Screens

Jeeves has no TipForm product UI. Operator surfaces are IRC commands, chair logs, webhook health, and the MONITORING agent. HTML mocks are out of scope until a status site is chosen (see UNKNOWN).

| id | file | state |
|----|------|-------|
| (none) | --- | no design-uat mocks yet |

## LOCKED

- Product path `/bobiverse/jeeves`; install `<ai root>\jeeves`; service name `ircJeeves`
- Chair nick `Jeeves`; shops `#{machine}`; workers `{machine}-{pid}`
- Give-up / NACK exclusions are exact-seat only (FR #5088); recycled fresh nicks are not blocked by a dead predecessor on auto-offer
- `needs_human` blocks every seat for auto-offer (FR #4336); only `!assign` may hand it out
- CAST IRON harvest + intake every session; never print secrets
- Hotpatch: never touch Ergo / `BobIrcd`; restart only `ircJeeves`
- MONITORING agent reports via intake and never `!assign` / queue edits

## UNKNOWN

- Future HTML / TipForm-style status surface for queue and webhook health (IRC + monitor scripts remain primary)
- Exact digest ghost-nick TTL vs live_seat_nicks under heavy report lag beyond FR #5088 exact-seat give-up
- Whether UAT dead-author inherit should ever narrow further after more recycle evidence
