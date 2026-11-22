---
name: bobiverse-jeeves-agent-seat-recycle
description: >
  Recycle a hung or out-of-fuel worker seat through the tray recycle queue
  (!recycle / recycleseat), honouring seat rules: seats start only from Si's
  clicks, MarchHare is OpenCode-only unless Si started a Grok/Cursor seat
  himself, explicit Cursor starts use Si's own account, never set MarchHare's
  seat target to 0. Use for hung seats, no ACK, out-of-tokens, or /bobiverse-
  jeeves-agent-seat-recycle.
depends_on:
  - bobiverse-jeeves-agent-seat-dispatch
---

# bobiverse-jeeves-agent-seat-recycle

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

## Recognise

- Hung: no ACK/DONE progress for well past the job window, digest `working_on` stale, stuck-doing check fires.
- Out-of-fuel: `GIVEUP ... out-of-fuel`, 402 / usage exhausted, chair `seat-out-of-fuel.json` mark.
- A failed or unknown fuel read is **not** exhausted.

## Recycle path

1. Preview: `!recycle dry-run <machine>` (ops). It shows the plan only.
2. Recycle goes through the tray recycle queue (`!recycle <machine>`, or chair stall-heal `recycleseat`);
   120 s cooldown. `!recycle jeeves` restarts only `ircJeeves` - never use it for a seat.
3. Busy seats are never recycled. Finish or release their job first.
4. After recycle: the new seat must say `!bored` in its own `#<machine>` and show in the digest.

## Seat rules (hard)

- **Seats start only from Si's clicks.** A recycle replaces a seat; it never adds seats or raises targets.
- **MarchHare is OpenCode-only** unless Si himself started a Grok or Cursor seat there; leave those alone.
- **Never set MarchHare's seat target to 0.**
- No redqueen Flash seat may become Grok.
- An explicit Cursor start uses Si's own Cursor account tokens (FR #8649 / #8667); never another account.
- Grok first, then Cursor, only for starts Si asked for.

## Stop rules

Out-of-fuel with no reset due: report, do not recycle in a loop. Repeated hangs on the same seat -> FR with
log evidence. Never kill processes you did not start.
