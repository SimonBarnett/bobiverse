---
name: bobiverse-bob-job-irc
description: >
  Exact IRC wire contract for worker jobs - !bored, Jeeves assign in !focus order, ACK, DONE, NACK/GIVEUP formats, which channel, when to send each, who sends what (the program posts !bored and pong, you write ACK/DONE to the outbox). Use whenever you take, finish or hand back a job.
---

# bobiverse bob - job wire: ACK, DONE, NACK, GIVEUP, !bored

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

You are a bob **worker seat**. This skill is the exact wire contract between you, the worker program (`bob-worker.exe`) and Jeeves for taking and finishing jobs.
It matches `docs/jeeves-commands.md` (row "shop wire") and Jeeves' shop listener grammar (`shop_listen.py`, FR #211). The three job skills build on it:
`bobiverse-bob-job-fr`, `bobiverse-bob-job-mrb`, `bobiverse-bob-job-uat`.

## Where you speak

* ONLY your own shop channel `#<machine>` (FR #224). Never a PM to anyone (not Jeeves, not `bob-*`, not simon, not another worker), never `#bobiverse`.
* You do not talk to IRC directly: append lines to the `outbox.txt` named in your first instruction. Write `PRIVMSG #<machine> :<line>` (a bare `<line>` also goes to the shop).
  One wire line per outbox line, UTF-8, ending in a newline. The program sends it as your nick `<machine>-<pid>`.
* The program (not you) answers `ping` with `pong` and posts `!bored`. **Never post `!bored` yourself** - a `!bored` in your outbox is refused and logged.

## The cycle

```mermaid
sequenceDiagram
  participant P as bob-worker.exe
  participant J as Jeeves (shop #machine)
  participant A as you (agent)
  P->>J: !bored (seat ready, or right after DONE, or idle 2 min then every 3 min)
  J-->>P: nick: TYPE owner/repo#N url   (next job in !focus order)  or  nick: nothing queued
  P->>A: FROM Jeeves #machine nick: TYPE owner/repo#N url
  A->>J: ACK TYPE owner/repo#N        (via outbox; Jeeves marks you accepted + busy)
  Note over A: work - the program stays silent while the ACK is open
  A->>J: DONE TYPE owner/repo#N [PASS or FAIL] url   (Jeeves marks you done + idle)
  P->>J: !bored  (immediately after DONE or NACK/GIVEUP - keep going)
```

1. The program posts `!bored` when your agent is ready, right after every DONE or NACK/GIVEUP, and while idle (first after 120 s, then every 180 s). It never posts while you hold an open ACK.
2. Jeeves assigns the next unaccepted job **in `!focus` order** (owner `!focus`/`!unfocus`, ignore list applied) with one shop line `<nick>: <TYPE> <owner/repo>#<N> <url>`,
   or `<nick>: nothing queued`. See your queue by PM with `!list` only if told to; do not type commands in the shop.
3. You get it as typed input: `FROM Jeeves #<machine> <nick>: FR SimonBarnett/bobiverse#7 https://github.com/...`. Only an assign line **addressed to your nick** is a job; a line for another nick is not yours.
4. **ACK first** (below), then work, then **DONE** (below). Jeeves: ACK -> accepted + busy; DONE -> done + idle. The first seat to ACK a row owns it; a sibling no-ops.

## ACK - exact format

```text
ACK <TYPE> <owner/repo>#<N> [short title]
```

* `TYPE` = the word Jeeves assigned: `FR`, `MRB` or `UAT` (the grammar also knows `PR`, `FIX`, `BUILD`). `owner/repo#N` exactly as assigned.
* Starts at column 0, **no nick prefix**, case-insensitive verb, one line.
* Send it **immediately** when you decide to take the job - before you read code or run anything. An un-ACKed seat looks idle: the program would post `!bored` and Jeeves could hand you a second job.
* Example: `PRIVMSG #marchhare :ACK FR SimonBarnett/bobiverse#7 restore !help`

## DONE - exact format

```text
DONE <TYPE> <owner/repo>#<N> [PASS|FAIL] <url>
```

* `TYPE` and `owner/repo#N` = the **assigned** values, even if the work turned into something else.
* At most one `PASS`/`FAIL`. FR: the PR url (no PASS/FAIL). MRB: `PASS` or `FAIL` + the PR url. UAT: `PASS` or `FAIL` (url optional: the release url on PASS - a PASS means no gaps, docs updated and the release created - or the UAT evidence comment / gap FRs on FAIL; a FAIL means an FR per gap and NO release).
* **One line, nothing after the url.** Fix-PR numbers, SHAs, caveats and follow-ups go on a SEPARATE outbox line or a GitHub comment, never on the DONE line.
* Send it only when the work is really finished (PR opened / verdict posted and merged / UAT stamped or failed). Send it **after** the evidence is in place, never before.
* Examples:
  `PRIVMSG #marchhare :DONE FR SimonBarnett/bobiverse#7 https://github.com/SimonBarnett/bobiverse/pull/9`
  `PRIVMSG #marchhare :DONE MRB SimonBarnett/bobiverse#9 PASS https://github.com/SimonBarnett/bobiverse/pull/9`
  `PRIVMSG #marchhare :DONE UAT SimonBarnett/bobiverse#7 PASS`

## NACK / GIVEUP - handing a job back

```text
NACK <TYPE> <owner/repo>#<N>
GIVEUP <TYPE> <owner/repo>#<N>
```

Same grammar, same effect: Jeeves returns the row to the unaccepted queue and marks you idle (the program posts `!bored` again immediately, `reason=free`, FR #161). Convention: `NACK` = you decline **before** doing any work (wrong repo,
no access, not your kind of job, duplicate); `GIVEUP` = you abandon **after** an ACK (blocked, out of time/tokens, the task is impossible). Put the reason on a separate line or a GitHub comment, then harvest it
(CAST IRON rule: file it). Never go silent on an ACKed job - a seat that ends is returned to the queue by Jeeves on QUIT, but a NACK/GIVEUP is faster and tells the next worker why.

## Rules

* ACK before work, DONE after work, one line each, assigned TYPE and id, nothing after the url, own shop only, never a PM, never `!bored`.
* No chatter while you hold a job and none after DONE: finish the turn. The next job arrives by itself.
* An outbox line starting `ACK`/`DONE`/`NACK`/`GIVEUP` is what the program uses to know you are busy or idle - do not write those words at the start of ordinary chat lines.
* Self-MRB or merging your own FR PR is forbidden; see the job skills for who owns what.
* File every problem with the contract (a job that never assigns, a parse miss, a wrong queue order) through intake - CAST IRON rule at the top.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No assign after `!bored` | Jeeves says `nothing queued`, the repo is ignored, or `!focus strict` excludes it. Ask the owner; PM `!status` / `!list` is read-only. |
| Assign came, ACK ignored | line had a nick prefix, wrong TYPE, or the id differs from the assign - copy it exactly. Check `cmd-trace.log` on the chair if you can. |
| Two assigns at once | you forgot the ACK (looked idle). ACK the first, `NACK` the second. |
| `!bored` never posts | open ACK without DONE/NACK/GIVEUP (busy), agent not ready/restarting, or IRC lost (the seat ends). See `bobiverse-bob-worker`. |
