---
name: bobiverse-jeeves-agent-seat-health
description: >
  Classify each worker seat as idle, busy, hung or out of tokens from the digest,
  fuel/quota fields and read-only worker logs; recommend restart or model switch
  with evidence but never perform one. Use for seat health, hung seats, token
  exhaustion, or /bobiverse-jeeves-agent-seat-health.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-seat-health

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Read-only seat classification for the Jeeves agent. Health context first:
`bobiverse-jeeves-agent-monitor`. Sources: public digest / `https://bob.ntsa.uk/bob/v1/report`
(`machines.*`, jobs, `running`/`queued`, `lastSeen`), fuel/quota fields, and the worker's
own logs on its machine (read-only). Public hosts only (`bob.ntsa.uk`, `irc.ntsa.uk`,
`github.com`). Never restarts, kills or recycles a seat.

## Thresholds

| Class | Rule |
|---|---|
| idle | `running=0` and `queued=0` (or empty `jobs`) and fresh `lastSeen` |
| busy | has an accepted / doing job with recent progress (wire ACK/DONE activity or digest progress within 15 min) |
| hung | busy (or `state=doing/offered`) with **no progress for 15 minutes** (`DOING_MAX_AGE_SEC` / monitor `seats_stuck_doing`); OpenCode `progress_phase=stream` heartbeats alone do not count as progress |
| out of tokens | quota/fuel remaining is 0, or worker/log shows a server refusal string such as `insufficient_quota`, `rate_limit_exceeded`, `tokens exhausted`, `billing`, or model `context_length` refusal that ends the turn |

Report times in Europe/London (convert UTC). Prefer token-free
`scripts\Invoke-JeevesMonitorCheck.ps1 -Check seats_stuck_doing` / `idle_seats` JSON over guessing.

## Report row (one per seat)

`machine | seat | class | evidence | recommendation`

- hung: recommend seat restart (Si only) with the stuck age and last wire line.
- out of tokens: recommend model switch or fuel top-up (Si only); never change `seat_target`.
- idle with ungated offerable work: report only (offer path is chair/monitor).
- busy healthy: no action.

## Seat rules (must respect)

- MarchHare: no Grok/Cursor seat unless Si starts it.
- redqueen Flash/OpenCode seats never become Grok.
- Never write `recycleseat.*` markers, never `clear_seat_doing` a working seat, never change `seat_target`.

## Steps

1. Pull digest/report JSON (public `bob.ntsa.uk` from off-chair hosts; chair-local digest home only on walrus).
2. Run monitor seat checks; note exit 0/1/2 JSON.
3. Optionally, on the seat's own machine only, tail worker logs with
   `Get-Content <worker>\logs\*.log -Tail 80 | Select-String 'DONE|GIVEUP|quota|token|rate_limit'`
   (never `inbound-transcript.log` / NSSM env / credentials).
4. Emit one row per seat. File hung/out-of-tokens findings via `bobiverse-jeeves-agent-incident-report` (de-dup first).

## Stop rules

- Stop before any restart, kill, recycle, or `seat_target` edit; those need Si's OK.
- Never invent remote log lines from a host you cannot read.

## Hard rules

- No secrets. Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time, each with a backup and a ROLLBACK.