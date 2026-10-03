<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path .grok/skills/jeeves-git-webhook/SKILL.md, last changed 2026-09-26. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
---
name: jeeves-git-webhook
description: >
  Git webhooks on the ionos digest listener, announced by Jeeves only.
  Use when the user says git webhook, webhooks from git, Jeeves announce,
  GIT pull_request, GIT push, chair-outbox, issue #147, !BORED, git-claim,
  or /jeeves-git-webhook. Digest working_on posts stay bob-irc.
---

# Git webhooks announced by Jeeves

Foundation: harvest-agent-skills (honesty box) -> report back to https://github.com/SimonBarnett/agentic_irc

Issue #147. Route is live: `POST /bob/v1/git` on the same ionos listener
as the digest. Jeeves (`irc_agent.py --chair`, nick `Jeeves`) is the only
nick that says `GIT`.

Digest `POST /bob/v1/report` (change-only, `X-Bob-Secret`) stays
`bob-irc`. Do not copy that playbook here.

## Announce path

1. GitHub POSTs the event. Header `X-GitHub-Event` is required. Peer IP
   must be in `BOB_REPORT_ALLOW`. No webhook secret in git, issues, or
   channel text.
2. `enqueue_chair_fleet_privmsg` appends
   `PRIVMSG #bobiverse :GIT …` to `chair-outbox.txt` on the digest home
   (`BOB_DIGEST_HOME` = `~\.agentic-irc-bobiverse`), not `outbox.txt`
   and not `~\.agentic-irc-jeeves`.
3. Only `irc_agent.py --chair` drains `chair-outbox.txt`.
   `fleet_digest_home()` reads `BOB_DIGEST_HOME`. Without that env the
   chair uses `--home` and GIT lines stay stuck on the digest home.
   `scripts/Install-BobChair.ps1` sets `--home` / `AGENTIC_IRC_HOME` to
   `~\.agentic-irc-jeeves` and `BOB_DIGEST_HOME` to
   `~\.agentic-irc-bobiverse`. Do not share `--home` with `bob-ionos`.
4. `bob-*` and talk seats drain `outbox.txt` only. They do not read
   `chair-outbox.txt` and they do not narrate `GIT` lines.
5. A `GIT` line already sitting in `outbox.txt` from before this split can
   still be spoken once by `bob-ionos`. New events must not go there.

## Line shape

`GIT <event> <owner/repo> … by <actor>` on `#bobiverse`. Known detail:

- `ping`: zen
- `push`: branch, 12-char SHA, `N commit(s)`
- `pull_request` / `issues`: action, `#n`, title

No fleet-status spam. No `!bobiverse` from a talk seat.

## Claim queue (`!BORED`)

The digest webhook is the list. `GET /bob/v1/report` (same body as
`/bob/v1/digest`) includes:

```text
queue.unaccepted[]   FIFO, not yet claimed
queue.accepted[]     claimed rows (nick, channel, accepted_ts)
```

`POST /bob/v1/git` appends a claimable event onto `queue.unaccepted` in
the same step that queues the `GIT` line. `POST /bob/v1/report` with
`X-Bob-Secret` and `{"op":"git-claim","nick":"…","channel":"…"}` returns
`200` `{"ok":true,"claimed":{…}}` and moves that oldest row to
`accepted` in the same write. Empty queue: `{"ok":true,"claimed":null}`.
Jeeves calls that op. It does not decide the row by reading a side file.
`queue.json` on the digest home is only the listener's crash mirror of
this list. Old `git-unaccepted.json` / `git-accepted.jsonl` are imported
once into that mirror and are not live.

Jeeves is if-then only. No model call. `bob-*` does not auto-claim.

Allowlist (anything else is skipped, including `ping`, `push`, `closed`,
`edited`, `synchronize`, `labeled`):

| GitHub event | action | `{task}` |
|---|---|---|
| `issues` | `opened` | `PR` |
| `pull_request` | `opened` | `MRB` |
| `pull_request` | `ready_for_review` | `MRB` |

Task vocabulary is `PR`, `BUILD`, `MRB`, `FIX`, `UAT`. This GIT map emits
only `PR` and `MRB`. `PR` is the issue→implement name.

Breaking change from the first draft of this flow: `!BORED` both offers
and accepts. A separate `!ACCEPT` is not required. If a worker still
sends `!ACCEPT {repo} {task} {id}`, Jeeves ignores it (no second claim).
`!TASK` is not used. `FILE v1 ACCEPT` is file transfer.

Jeeves already JOINs every shop, so it hears `!BORED` itself.

Worker, on **its** shop (`#flamingo`, `#ionos`, `#marchhare`,
`#ce-priority-dev1`):

0. **CAST IRON (Simon 2026-09-26):** `!BORED` / `!bored` is sent by the seat
   **monitor** only, never by the model, and never while a `-p` run is alive or
   an ACKed job lacks a valid DONE. See `bob-git-accept` (agentic_build) for the
   exact **DONE** wire.
1. (monitor) Do not send `!BORED` until this worker has had no job for more than
   120 seconds.
2. (monitor) Send exactly `!BORED`.
3. Jeeves claims / assigns the next row and replies with the assign line
   (`<nick>: <TYPE> <repo>#<n> <url>` on modern FR #106 chairs).
4. Start work. `POST /bob/v1/report` `op=merge` with `working_on` set to
   that job, plus `agent` and `model` when you know them
   (`post_working_on.py --working-on '…' --agent … --model …`).
5. When the job is done: outbox the exact DONE line from `bob-git-accept`, then
   POST `state=idle` (`--idle`). That clears `working_on`, `agent`, and `model`.
   Do **not** post `!bored` yourself.

Chair gate before it calls `git-claim`:

- Not a `w-*` nick, or not that worker's shop → silence.
- Shop activity newer than 120 seconds → `NAK !BORED wait`.
- Digest `working_on` for that worker pid is non-empty →
  `NAK !BORED busy`.
- Webhook returns no row → `no jobs`.
- Webhook POST fails → silence (no invented job).

`git-worker-activity.json` on the chair home is only that 120-second
gate. It is not the job list. Shop chatter from the `w-*` updates it.
`NAK !BORED wait` does not.

After PASS-nits merge to `main`, ionos must recycle Jeeves and
`bobcallback` (`!recycle ionos`). Until that recycle, new events are not
queued and shop `!BORED` gets no answer. Also recycle `bob-*`
Watch-Bobiverse so each ear runs the merged tree. Those ears do not
emit a claim.
