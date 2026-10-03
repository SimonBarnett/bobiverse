<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-bob-grok-irc-listen-talk-worker-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Grok-talk worker (consume IRC inbox, write completions)

**Plan:** `docs/build-and-test-plan-bob-grok-irc-listen-talk-worker-2026-09-21.md`
**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**Sister (hook + wire, landed on agentic_irc #56):**
`docs/grok-talk-envelope-v1.md`,
`docs/feature-request-bob-grok-irc-listen-talk-2026-09-21.md`
**Raised by:** Hostile MRB of agentic_irc SHA `a924f9e5fa7ab5cd2167fd0c0bc7713e54588b5d`
**UAT + hostile MRB owner:** Bob

## Problem

agentic_irc #56 defines the **hook** only: `irc_agent` appends
`~\.agentic-irc-bobiverse\grok-inbox.jsonl` when `grok_talk_enabled` and
peer `weekly` > 0, and drains `grok-outbox.jsonl` into `outbox.txt`.
No worker in this repo reads that inbox or writes completions. Addressed
English on `#bobiverse` still stops at the canned ACK until a sister
consumer exists.

This repo already owns fuel (`Get-BobWeeklyRemaining` / tray /
`Select-BobGitWorker`) and short-lived workers (`Start-BobWorker`).
Watch-Bobiverse stays **no grok.exe**.

## LOCKED

1. **Consume** `AGENTIC_IRC_HOME\grok-inbox.jsonl` (fleet default
   `~\.agentic-irc-bobiverse`). Envelope v1 fields: `v`, `job_id`, `ts`,
   `asker`, `channel`, `body`, `nick`, `machine_id`, `reply_target`,
   `body_hash` (see agentic_irc `docs/grok-talk-envelope-v1.md`).
2. **Complete** by appending one JSON line to `grok-outbox.jsonl`:
   `{v:1, job_id, reply_target, lines: string[]}`. One English fact per
   line, cap 350. Secrets-shaped text must not be written
   (`looks_like_secret` / drop).
3. **Fuel.** Do not start a grok-talk job when Grok Build weekly is 0
   unless Cursor Models remaining > 0 (or an explicit Grok Bot desktop
   path). Prefer Cursor Models when remaining > 0. Never Other Models.
   Do not burn Grok Bot weekly when Cursor Models or grok.exe can take it.
4. **Watch stays dumb.** No grok.exe inside `Watch-Bobiverse.ps1`.
   Start a short-lived worker (BobBridge / `Start-BobWorker` or a sibling
   poller). Max concurrent grok-talk jobs per machine: **1**.
5. **No secrets** in git, prompts, or on the IRC wire. Instructional
   mentions of the names are OK. No `password` or API-key **assignments**.
6. Off-DEV Test-Pack / fake inbox+outbox. No live Ergo. No live grok in CI.
7. PR only. Worker does not stamp UAT.

## UNKNOWN

- Poll vs notify (Watch tick vs dedicated `grok_talk` poller).
- Whether the worker is a named Grok Bot on the box or a Cursor Models
  / grok.exe one-shot via `Start-BobWorker`.
- Shop `#ionos` vs fleet-only: IRC hook already replies on the ask
  channel / Query. Sister must honour `reply_target`.

## Gap vs tree

| Current | Wanted |
|---|---|
| Fuel + `Start-BobWorker` exist | A grok-talk consumer that reads the IRC inbox |
| Tray weekly gate | Same gate before starting a listen-talk job |
| No `grok-inbox.jsonl` reader | Completions in `grok-outbox.jsonl` |

## Acceptance

- **AC1** Fake inbox line + fake worker stdout/completion produces a
  matching `grok-outbox.jsonl` record (`job_id`, `reply_target`, `lines`).
- **AC2** weekly=0 and Cursor Models remaining=0 → no worker start.
- **AC3** Watch-Bobiverse still has no grok.exe import / start.
- **AC4** Test-Pack green off-DEV. No secret assignments in repo.

## Non-goals

- Changing the agentic_irc hook / envelope (that is #56).
- LLM inside Watch-Bobiverse.
- `!report` write. POINT firehose.
- MRB PDF.
