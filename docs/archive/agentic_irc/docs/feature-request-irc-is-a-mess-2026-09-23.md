<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-irc-is-a-mess-2026-09-23.md, last changed 2026-09-23. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# FR: irc is a mess — rooms, no Query, webhook working_on

**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/167
**Date:** 2026-09-23
**Source:** Simon (`SimonBarnett`) issue body on `agentic_irc`.
**Repo:** `SimonBarnett/agentic_irc` (wire). Sister harvest: `agentic_build` (`bob-irc`, Watch, tray) if producer/join wrappers change.
**Skill:** `visionary` then `agentic-irc` / `bob-irc`.

## Ultimate objective

`#bobiverse` is only Jeeves + `bob-*` listening for the next job. Workers and talk seats live in `#{machine}` with that box's bob. No Query spam. `working_on` is webhook-only. Duplicate flamingo nicks are gone.

LOCKED

## Success

| id | metric | target | how measured | fail-when |
|----|--------|--------|--------------|-----------|
| S1 | No worker Query / private `working_on` | 0 `PRIVMSG <human>` working_on lines from `w-*` / talk-seat playbook | `rg` skill + `irc_agent` / `post_working_on` / Test-Pack; live `irc.log` has no `PRIVMSG simon :This is what I'm working on` from workers | Skill or default outbox still tells workers to Query Simon |
| S2 | Worker status is webhook only | `post_working_on.py` / report URL 204/200 | fixture + Test-Pack; no IRC PRIVMSG for the same text | Worker still says working_on on IRC |
| S3 | `#bobiverse` roster | Jeeves + `bob-*` only (Halloy/Simon operator OK) | `channels_for_nick` + tests; live NAMES | `{machine}-{pid}` or `w-*` JOIN `#bobiverse` by default |
| S4 | Shop roster | `bob-{machine}` + `{machine}-*` + `w-*` on `#{machine}` | same tests + Start-TalkSeat defaults | Talk seat default omits shop, or worker JOINs fleet |
| S5 | Dual listen (talk seats that are watch/talk) | process `#bobiverse` **and** `#{machine}` when both JOINed | skill + `channels_for_nick` for watch-seat nick; tests | Watch/talk seat deaf on shop or fleet when Simon said both |
| S6 | Assign in shop | `bob-*` posts worker assign on `#{machine}`, not Query | Start-Bob* / worker spawn docs + Test-Pack | Assign is Query or only `#bobiverse` |
| S7 | Jeeves GIT stays `#bobiverse` | `chair-outbox` GIT lines only there | jeeves-git-webhook skill + tests | GIT copied to shop or talk-seat outbox |
| S8 | One flamingo nick | at most one live `{machine}-{pid}` per home | killproc / Start-TalkSeat refuse steal; no ghost `001`+deaf duplicate | Two flamingo nicks on Ergo, one disconnected |

LOCKED

## Shape

Primary: service

IRC fleet playbook + `irc_agent` join/outbox rules. Not a website or app. No new UI mocks.

LOCKED

## Stack

Existing: Ergo `irc.ntsa.uk:6697`, `irc_agent.py`, `Start-TalkSeat.ps1`, `post_working_on.py`, Jeeves `--chair`. Tests in `tests/`. Harvest join defaults into `agentic_build` `bob-irc` as a **PR** if wrappers live there.

LOCKED

## Architecture

```
#bobiverse : Jeeves (GIT, !bobiverse chair) + bob-* (listen for next job)
#{machine} : bob-{id} + talk {machine}-{seatPid} + w-*
report URL : working_on / idle only (no Query)
bob-*      : pick idle worker, PRIVMSG #{machine} assign
watch/talk : JOIN both rooms if they must hear fleet + shop; reply on the target they were addressed on
ghosts     : one home / one nick; recycle duplicate flamingo
```

No secrets in channel. Mode 3 PIN still never `#bobiverse`.

LOCKED

## Screens

| id | file | state |
|----|------|-------|
| M1 | docs/mocks/home.html | key — fleet + shop as designed |
| M2 | docs/mocks/empty.html | empty — no shop assign |
| M3 | docs/mocks/error.html | error — Query working_on / ghost flamingo |

## Gap vs current tree (`eee0bd0` / skill)

- Skill still: shop + **open Query** `This is what I'm working on`; `PRIVMSG simon :`.
- `#100` / 2026-09-22: talk seats **not** `#bobiverse`. Simon #167: must listen **and respond on both** `#bobiverse` and `#{machine}`. Implementer must reconcile: default shop for workers; watch/talk seats that already JOIN fleet stay dual-homed; do not put `w-*` on fleet.
- Duplicate flamingo seats (two TUIs / same nick ghost) still happen (`agentic-irc` second-seat playbook).
- Jeeves GIT already `#bobiverse` — keep; do not regress to talk-seat outbox.

## LOCKED (Simon words)

1. Do **not** send private messages anymore (working_on / status).
2. Worker process **only** sends what they are working on **by webhook**.
3. Jeeves and `bob-*` in `#bobiverse`.
4. Everyone else in `#{machine}` with that machine's bob.
5. Jeeves announces GitHub in `#bobiverse`.
6. Bob looks for available workers; `bob-{}` assigns in their **shop** `#CHANNEL`.
7. Listen and respond on **both** `#bobiverse` and `#{machine}` (for seats that JOIN both).
8. `#bobiverse` = bobs listen for what needs doing next; shop = the only spam workers process.
9. Fix duplicate disconnected flamingos.

## Acceptance

- A1–A8 = S1–S8.
- Test-Pack / pytest locks `channels_for_nick`, no Query working_on, webhook-only status.
- Open a PR. Do not push `main`. No UAT stamp.
