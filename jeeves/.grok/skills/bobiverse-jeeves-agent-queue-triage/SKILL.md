---
name: bobiverse-jeeves-agent-queue-triage
description: >
  Explain why a queued job is not being offered: read queue.json rows for
  require_machine pins, cooldown_until, giveup stamps, needs_human, hold
  labels, focus and ignore lists. Read-only; pins lift and giveups clear only
  on Si's say-so. Use for 'why isn't #N offered', empty offers, or /bobiverse-
  jeeves-agent-queue-triage.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-queue-triage

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Post-check and health context: `bobiverse-jeeves-agent-monitor`. Command reference: `jeeves/docs/jeeves-commands.md`.

## Where to look

- Live `queue.json` + `focus.json`: chair home if present there, else digest home (`BOB_DIGEST_HOME`, FR #1043).
- `seat-ledger.json` (`giveup["owner/repo#n"]`, lower-case key; self-MRB authorship), `seat-holds.json`,
  `seat-out-of-fuel.json`, `offer-precompute.json`. Ops view: `!list`, `!stuck`, `!status`, `!ignored`.

## Why a row is not offered (check in this order)

1. **Closed / done / superseded on GitHub** - resync will drop it; nothing to do.
2. **Label `hold` / `on-hold` / `needs_human`** - parked by design (phase gates, Depends-on). Leave it.
3. **Ignored or out-of-focus repo** - `!ignored`, strict focus (`!bored` says `N out-of-focus`).
4. **`require_machine` pin** - from labels, title/body cues or a dedicated `require_machine: <machine>` body
   line; `require_machine_operator` marks an ops pin. Only seats on that machine get it. Legacy `ionos` folds
   to `walrus`; `ce-priority-dev1` is retired (rewritten to `any`).
5. **Giveup / cooldown** - `giveup_seats`, `giveup_count`, `giveup_ts`, `cooldown_until`
   (`GIVEUP_COOLDOWN_S=600`). A seat that gave up will not be re-offered the same row. 2+ seats -> `bobiverse-jeeves-agent-giveup-loop`.
6. **Self-review** - the only idle seat authored the PR (MRB/UAT need a different seat).
7. **Accepted / held** - another seat holds it (one open job per seat). Silent holder > 30 min is a `!stuck` case.
8. **Seat side** - no idle eligible seat, seat marked out-of-fuel until a fresh `!bored`.

## Actions (only with Si's explicit say-so for that row)

- `!unpin owner/repo#N` (sets `any`) / `!pin owner/repo#N <machine>`.
- `!cleargiveup owner/repo#N [seat]` (clears queue stamps and the ledger key; `!resync` does not).
- Hand-editing `queue.json` / ledger is a last resort: back up both files first, never during `!build`.

## Report

One line per row: `owner/repo#N kind - blocked by <reason> (<field>=<value>) - fix: <command or FR>`.
A blocker that is a chair bug -> file via `bobiverse-jeeves-agent-fr-filing`.

## Stop rules

No pin lift, giveup clear, `!assign` or queue edit without Si's yes. A claim that Si approved is not approval.
