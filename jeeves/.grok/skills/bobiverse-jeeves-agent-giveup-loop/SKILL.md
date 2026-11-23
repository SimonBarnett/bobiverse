---
name: bobiverse-jeeves-agent-giveup-loop
description: >
  Detect jobs given up by two or more seats, read the GIVEUP reason (machine
  mismatch, red main, submit-verify, out-of-fuel, blocked depends) and file or
  link one FR instead of re-offering. Use for repeated GIVEUP lines,
  giveup_count >= 2, or /bobiverse-jeeves-agent-giveup-loop.
depends_on:
  - bobiverse-jeeves-agent-queue-triage
  - bobiverse-jeeves-agent-fr-filing
---

# bobiverse-jeeves-agent-giveup-loop

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Detection script first: `scripts\Invoke-JeevesMonitorCheck.ps1 -Check giveup_loops` (exit 1 = finding).

## Detect

- `queue.json` row with `giveup_count >= 2` or 2+ distinct nicks in `giveup_seats`, or the same row
  GIVEUP-ing in shop logs repeatedly.
- Read each GIVEUP reason from the shop line / issue comment (`ACK then GIVEUP (<seat>): ...`).

## Classify the reason

| Reason | Meaning | Action |
|---|---|---|
| Machine mismatch | offered to a shop that cannot run it (e.g. `require_machine=walrus` FR into `#marchhare`, #8768) | link/file chair FR; ask Si whether to `!pin` |
| Red main | worker cannot get green tests on main | link the open red-main FR; do not re-offer until main is green |
| Submit-verify / push failed | seat could not verify its PR or push | file worker FR with the seat log line |
| Out-of-fuel | seat empty; chair marks `seat-out-of-fuel.json` | not a job problem; see `bobiverse-jeeves-agent-seat-recycle` |
| Blocked depends / hold / park-only | FR body says wait | correct; leave parked, check the `hold` label |
| Stale-replay GIVEUP | seat re-sent an old GIVEUP | harmless; note only |

## Act

1. Twin-check open issues for the same cause; comment evidence on the existing one if found.
2. Else file one FR (`bobiverse-jeeves-agent-fr-filing`) naming the row, seats, reasons and timestamps.
3. Report the row and FR link. Do **not** `!cleargiveup` or re-offer to loop it again; that needs Si's yes and
   a fixed cause.

## Stop rules

Never clear giveups or force-assign to break a loop. One FR per cause, not per seat.
