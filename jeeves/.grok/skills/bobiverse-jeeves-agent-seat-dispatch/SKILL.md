---
name: bobiverse-jeeves-agent-seat-dispatch
description: >
  Offer and assign rules for worker seats: priority/critical first, then MRB
  before UAT before FR, lowest number first; free seats get FRs first, Grok
  seats saved for MRB; hostile MRB from a different seat than the author; when
  and how !assign is used if the queue stalls. Use for dispatch decisions,
  idle seats with work queued, or /bobiverse-jeeves-agent-seat-dispatch.
depends_on:
  - bobiverse-jeeves-agent-queue-triage
---

# bobiverse-jeeves-agent-seat-dispatch

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Jeeves offers deterministically on `!bored`; this skill is how an operator/agent judges whether it did right
and what to recommend when it stalls.

## Offer order (chair, FR #3205 / #7204)

1. Label `priority/critical` first (oldest, then lowest number).
2. Within focus priority: **MRB, then UAT, then FR**; **lowest issue/PR number first**.
3. A seat ineligible for the waiting MRB/UAT still gets the next eligible FR.

## Seat choice (fleet policy)

- **Free seats get FRs first** (OpenCode / free models). Paid credit is scarce.
- **Grok seats are saved for MRB.** An FR goes to Grok only when no free seat can take it.
- **Hostile MRB comes from a different seat than the author** (seat ledger blocks self-MRB/UAT).
- Respect `require_machine` pins and seat models; never move a running seat mid-job.

## When the queue stalls

Stall = offerable rows + idle eligible seats + no offer for several minutes (or `nothing queued` while
`!list` shows work). First triage the row (`bobiverse-jeeves-agent-queue-triage`). Then:

- `!assign <worker-nick> <repo> <FR|MRB|UAT> <num>` - ops only (owner / `bob-*` ears); `!assign` is Bob's
  (the ear's) to send. Rules: seat idle, row queued and unaccepted, no self-MRB, pin matches the seat.
- One assign per seat; wait for ACK before the next. No `!assign` to a seat that has not said `!bored`.
- A real chair bug behind the stall -> FR, not repeated hand-assigns.

### FR #9461 / #9878 - MONITORING intervene (token-free)

Deterministic idle+offerable intervene (not a standing LLM `!assign` loop):

1. **Prefer ear-relay** `PRIVMSG #bobiverse :!assign ...` via `intervene_assign` / ear outbox while chair
   `cmd-trace.log` is live (FR #9461).
2. **When ear mute / cmd-trace stale** (missing or older than `BOB_CMD_TRACE_MUTE_S`, default 120s):
   dispatch as Jeeves service shop-wire into chair outbox (`BOB_CHAIR_OUTBOX` or `~/.jeeves/outbox.txt`):
   `PRIVMSG #<machine> :<nick>: TASK owner/repo#N <url>` plus
   `PRIVMSG #bobiverse :assign: sent ...` (FR #9878). Helper: `Send-JeevesShopAssign.ps1`.
3. **Live mute incidents** that must write the **walrus** chair outbox: `require_machine=walrus`
   (pair with #9871/#9872). Durable helper + tip tests may use path override from any host.

## Stop rules

Do not run standing LLM `!assign` / `!sweep` loops. Token-free intervene (#9461/#9878) and chair
`push_idle_offers_via_chair_outbox` are the sanctioned bridges; recommend hand `!assign` only when
those paths are unavailable.
