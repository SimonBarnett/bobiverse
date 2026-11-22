---
name: bobiverse-jeeves-agent-queue-triage
description: >
  Read-only digest and queue triage for the Jeeves chair: table of offered,
  accepted and stale jobs with age, suspected cause and evidence. Flags START
  tiles that never cleared, #8738 mid-turn assign / done-miss, self-review
  deadlock and GIVEUP loops. Observe only; never writes ledger, queue or
  digest. Use for 'why is the queue stuck', stale START, missed DONE, or
  /bobiverse-jeeves-agent-queue-triage.
depends_on:
  - bobiverse-jeeves-agent-monitor
---

# bobiverse-jeeves-agent-queue-triage

> **CAST IRON RULE - HARVEST AND FILE EVERYTHING (read this first, every time).**
> 1. File every issue / FR / bug / gap you find in the SAME turn via the intake webhook (`https://bob.ntsa.uk/bob/v1/intake`):
>    `.\scripts\Report-BobiverseIntakeIssue.ps1 -Repo SimonBarnett/bobiverse -Kind issue -Title "short title" -Body "what / where / evidence / fix"`
> 2. Before finishing, run `.\scripts\Invoke-BobiverseHarvest.ps1 -Summary "..." -Lesson "..."` then `-Flush`.
> 3. Never put a token, password, SASL/NickServ secret, oper credential, key or private hostname in a filing, a skill, IRC or a log.

Health context first: `bobiverse-jeeves-agent-monitor`. Acting counterpart (intervene to keep the queue moving): #8681 / `bobiverse-jeeves-agent-seat-dispatch`. This node **only observes**.

## Where to look

| Source | On chair (walrus) | Off chair |
|---|---|---|
| Live digest | `C:\Users\Administrator\.bobiverse\digest.json` or `GET http://127.0.0.1:7700/bob/v1/report` | **Only** `GET https://bob.ntsa.uk/bob/v1/report` |
| Queue + focus | chair home / digest home `queue.json`, `focus.json` (`BOB_DIGEST_HOME`, FR #1043) | Public digest seats/jobs only; do **not** invent chair-local findings |
| Seat ledger / holds / fuel | `seat-ledger.json`, `seat-holds.json`, `seat-out-of-fuel.json`, `offer-precompute.json` | Unavailable off chair; skip |
| Self-review deadlock | digest home `mrb-reviewer-deadlock.json` | Report only if public digest already shows the MRB stuck on the author seat |
| Timed evidence | chair home `cmd-trace.log` (convert UTC to Europe/London) | Shop assign lines / issue comments only |

J: skill root reminder: `J:\.grok\skills` = `C:\ai\jeeves\.grok\skills` (share `Jeeves` on walrus), laid by `Install-Jeeves.ps1`.

## Hard rules

- **No secrets.** Never print or open tokens, passwords, webhook keys, NSSM env values, `config\oper.cred`, `identity.json`, `_backup-nssm-env-*`, `inbound-transcript.log` or any passwords folder. Placeholders and paths only.
- Never edit the Jeeves ledger, `queue.json`, outbox or digest by hand.
- No `!assign`, no `!focus`, no fake `ACK` / `DONE` / `!bored` / `GIVEUP`, never `!build cancel`.
- Restarts of `ircJeeves`, seats or services only on Si's explicit OK. `ErgoWalrus` needs Si's OK every time. Never restart Jeeves while a build runs.
- One machine at a time for any install/recover path; each with a backup and a ROLLBACK (hand off; this skill does not install).
- Off the chair host: use the public digest only; raise **no** chair-local health/queue/stale-digest findings from a non-chair host (FR #8579 / #8651 class).

## Triage pass (read-only)

1. Confirm host role. Chair = can read local files + `:7700`. Otherwise public digest only.
2. Pull seats and jobs from the digest. Note `running`, `queued`, `lastSeen`, offered/accepted rows and any START tiles.
3. On chair: parse `queue.json` rows (accepted age, `giveup_*`, `cooldown_until`, `require_machine`, hold labels). Check `mrb-reviewer-deadlock.json` freshness.
4. Cross-check cmd-trace / shop lines for ACK without DONE before the next offer (#8738 class).
5. Emit the table below. File or comment per the twin rules. Do not write or assign.

## Output table (required)

Produce one markdown table with these columns:

| job | seat | state | age | suspected cause | evidence | existing issue |
|---|---|---|---|---|---|---|

- **job** - `owner/repo#N` and kind (FR/MRB/UAT) when known.
- **seat** - nick or `-` if unoffered.
- **state** - offered / accepted / START / GIVEUP / idle-with-job / unoffered-blocked.
- **age** - wall time since offer/accept/START (operator zone Europe/London).
- **suspected cause** - short class name from the catalogue below.
- **evidence** - issue numbers, seat, cmd-trace or digest timestamps (London), field=value snippets.
- **existing issue** - open twin to comment on, or `-` if filing new / none.

Empty queue with healthy idle seats is a valid one-line report (`no rows to triage`).

## Cause catalogue

| Suspected cause | What you see | Action |
|---|---|---|
| Mid-turn assign / done-miss (#8738) | Seat ACKed job A; chair offered job B before A's DONE settled; digest may show B accepted while A unfinished | **Comment on #8738** with seat, both issue numbers and London times. Do **not** file a twin |
| Stale START tile | Digest/TipForm shows START on a seat with `running=0` and no live worker process | Report; worker clears its own activity. Never edit the digest |
| Self-review deadlock | `mrb-reviewer-deadlock.json` fresh, or MRB offered only to the PR author seat | Report (FR #5164 / #6256 class); hostile MRB needs another seat |
| GIVEUP loop | `giveup_count >= 2` or 2+ seats in `giveup_seats` | Hand to `bobiverse-jeeves-agent-giveup-loop`; do not clear or re-offer |
| require_machine pin | Row pinned; no idle seat on that machine | Report pin and idle shops; lifting needs Si (`!unpin`) via ops, not this skill |
| Cooldown / giveup stamp | `cooldown_until` in future or seat in `giveup_seats` | Report; clear only with Si's yes |
| hold / needs_human / out-of-focus | Labels or focus/ignore keep the row parked | Leave parked; note the label or `!ignored` |
| Accepted holder stuck | Accepted > 30 min (FR #5510) with dead/idle holder | Report as `!stuck` class; never `clear_seat_doing` a live seat |
| No eligible idle seat | Offerable rows exist; every seat busy, out-of-fuel or wrong machine | Report counts; recycle/fuel is another skill |
| Closed on GitHub | Row still in queue but issue closed | Resync will drop it; nothing to file |

## Twin and filing rules

- #8738-class rows: comment evidence on **#8738**; never open a second issue for the same mid-turn assign / done-miss class.
- Other findings: twin-check open issues first (`bobiverse-jeeves-agent-fr-filing`); comment on the first match; else file one FR with the table row as evidence.
- Never post ACK/DONE/`!bored`/GIVEUP for a seat. Never `!assign`.

## Verify

Triage is complete when every non-idle digest/queue row has a table line (or an explicit skip reason for off-chair limits), times are Europe/London, and any #8738-class row cites #8738 rather than a new issue.

## Stop rules

- Stop and escalate on any secret in output; redact before quoting.
- Stop if the next step needs a write, pin lift, giveup clear, assign, restart or install: hand to Si / the acting skill.
- Do not repeat the same table to rooms when nothing changed since the last pass.
