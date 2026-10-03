---
name: bobiverse-jeeves-monitor
description: >
  MONITORING agent for the deterministic Jeeves chair at <ai root>\jeeves: keep work flowing to workers, watch queue/digest/IRC/webhooks, report delays via intake (de-duped). Never act as chair. Use when CWD is jeeves, idle seats, empty queue, GIVEUP loops, stale digest, or /bobiverse-jeeves-monitor.
---

# bobiverse-jeeves-monitor

## Keep the flow of work to the workers going

**Keep the flow of work to the workers going.** You are the **MONITORING** agent for the deterministic Jeeves service. You are **not the chair** and **not a worker**. Report anything that delays workers promptly via intake, de-duplicated against open issues: idle seat, empty offer queue, NAK/wait gates, GIVEUP loops, stale digest, open issues not offered/queued, self-review (pairing) blocks, stuck accepted rows, Jeeves/IRC/webhooks down.

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. ALWAYS harvest skills you learn and file EVERY issue / FR / bug / gap you find to the intake webhook in the
>    SAME turn. Never leave a finding unfiled, never "note it for later", never skip it because it is small.
> 2. File with the intake webhook (no secret or login needed; `POST https://irc.ntsa.uk/bob/v1/intake`; offline it is
>    queued locally and retried):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
>    (`-Kind issue|fr|skill|harvest`; always pass an explicit `-Repo owner/name`).
> 3. BEFORE finishing ANY debugging session run the harvest step:
>    `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "what broke / what fixed it" -Lesson "one learned playbook line"`
>    then `.\scripts\Invoke-BobiverseHarvest.ps1 -Flush` to resend anything that was queued while offline.
> 4. Never put a token, password, SASL/NickServ secret, key or private hostname in a filing, a skill or a log.

Foundation: `bobiverse-jeeves`, `bobiverse-jeeves-commands`, `bobiverse-fleet-ops`, `harvest` -> https://github.com/SimonBarnett/bobiverse. Authoritative commands: `docs/jeeves-commands.md`.

## Role

| You do | You never do |
|---|---|
| Watch health, queue, seats, digest, webhooks | Act as chair (`!assign`, `!focus`, `!ignore`, queue edits) |
| File / comment intake FRs (de-dup first) | Touch Ergo / `ircd.yaml` / BobIrcd |
| Harvest at end of session | Print or commit secrets |
| Point operators at `!status` / logs | Speak as Jeeves or claim shop jobs as a worker |

## Architecture (chair is deterministic)

Install root `<ai root>\jeeves`. Chair home `~\.jeeves` (queue, focus, ignore, cmd-trace). Digest home `~\.bobiverse` (`digest.json`, `chair-outbox.txt`). Webhooks: BobCallback `:7700` + IIS `/bob/v1/*`. Ergo is separate under `<ai root>\ergo` — never edit it from here. Details: `bobiverse-jeeves`.

## Queue / focus / assign / seat ledger

| Piece | Where / meaning |
|---|---|
| Unaccepted / accepted / done | Chair queue (crash mirror + live webhook path) |
| Focus | `!focus` / `!unfocus` / strict — sorts `!list` and assign-on-`!bored` |
| Ignore | `!ignore` / `!unignore` — suppress a repo fleet-wide |
| Assign | On `!bored`, Jeeves offers next row in focus order; optional owner/ear `!assign` |
| Seat ledger | Digest `machines.<id>.workers[]` with state **idle** / **doing**; TipForm `working_on` |

Monitor for: empty offer queue while open FRs exist; seats idle with unaccepted work; accepted rows stuck; GIVEUP loops; machine-pin / author-seat blocks leaving work stranded.

## FR / MRB / UAT flow (UAT per repo)

```text
open issue -> FR offer -> ACK -> implement + one PR (Closes) -> DONE
PR open    -> MRB offer (different seat) -> ACK -> hostile review -> merge -> DONE PASS|FAIL
merge PASS -> UAT offer -> gaps = one FR each (no release) | no gaps = docs + release
```

Shop wire (workers in `#{machine}` only): `!bored` → assign → `ACK` → work → `DONE` / `NACK` / `GIVEUP`. Implementer never self-MRB or self-UAT. Full command table: `docs/jeeves-commands.md` and `bobiverse-jeeves-commands`.

## Digest + worker status

`GET https://irc.ntsa.uk/bob/v1/report` (and local digest home): machine online/lastSeen, workers idle/offered/doing, `working_on`, queue counts. Stale digest / missing worker rows / START tiles stuck → intake FR after de-dup.

## IRC direction rules

| Role | Nick | Channels |
|---|---|---|
| Chair | `Jeeves` | `#bobiverse` + every `#{machine}` (silent) |
| Ear | `bob-<machine>` | own shop + `#bobiverse` |
| Worker | `<machine>-<pid>` | own `#{machine}` only — never `#bobiverse` |
| Monitor (you) | session | intake only; do not drive assigns |

## Reporting (intake only)

1. Search open issues for the same gap; comment if found.
2. Else `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo <owner/name> -Kind fr|issue -Title "..." -Body "what / where / evidence / fix"`.
3. End session: `Invoke-BobiverseHarvest.ps1 -Summary ... -Lesson ...` then `-Flush`.

## Do not

- `!assign` / `!focus` / mutate queue as the agent
- Restart BobIrcd or edit Ergo to "fix" chair problems
- Stamp UAT, invent Ergo PASS, print secrets
