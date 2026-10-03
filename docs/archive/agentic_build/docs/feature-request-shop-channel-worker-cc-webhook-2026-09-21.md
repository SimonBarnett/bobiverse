<!-- ARCHIVED COPY - source: SimonBarnett/agentic_build @ 12f8758, path docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: shop channels + worker attach + write-only reportUrl

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_build
**GitHub issue:** https://github.com/SimonBarnett/agentic_build/issues/124
**Protocol sister:** https://github.com/SimonBarnett/agentic_irc/issues/46
**Raised by:** Simon
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob — `Start-BobBuild -Task git`

Private legion. Protocol canon is `agentic_irc` FR shop-channel (issue #46).
This repo owns Watch, skills that start MRB/build agents, and the ionos
write-only callback process.

## LOCKED (copy of sister — do not fork)

- Shop `#<machine-id>`. Worker JOIN shop only. Nick `w-<shortid>-<pid>`.
- Key `<machine-id>:<pid>`.
- `working_on` = “This is what I’m working on.”
- Shop = conversation stdout. Traces + tool xscripts → open Query only.
- Digest not public. No GET. Read = `!bobiverse` on IRC.
- Write = POST `reportUrl` + IRC JOIN/QUIT.
- `!report` scrubbed.
- Worker disconnect **deletes** worker JSON.
- Bob disconnect → machine stays (`I am offline`), shop closed, workers gone.
- No secrets in git/prompts/IRC.

Full wire + JSON: `agentic_irc/docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md`.

## Ask (this repo)

### 1. `config/bobiverse.json`

Add `reportUrl` (write URL on ionos, no read URL) and keep nicks table
as the only machine list. Shortids: fl / mh / io / d1.

### 2. Watch-Bobiverse

`bob-<id>` JOINs `#bobiverse` and `#<id>`. On local `irc_agent` death:
POST `shop-down` if Bob died, else `delete-worker` for that pid.
Do not append POINT / `!report` to outbox.

### 3. MRB/build skills (`bob-hostile-mrb`, `cursor-mrb-dev`,
`bob-build-dispatch`, `start-bob-cursor`, `grok-build-fleet`)

On start:

1. Resolve machine id from `bobiverse.json` (not hostname).
2. Attach `irc_agent` nick `w-<short>-<pid>` to `#<id>`.
3. Set `working_on` from the git-task title. POST merge.
4. CC visible assistant text to shop. If a human PMs the worker nick,
   also CC thinking + tool transcripts to that Query.
5. On process exit: QUIT shop (briefer deletes pid). If QUIT never
   leaves the box, Watch POSTs `delete-worker`.

### 4. Write-only listener (ionos)

POST `/bob/v1/report` only. 204/400/401/403. GET → 404/405.
Secret header `X-Bob-Secret` from `~\.grok\bob\report.secret`.
Allowlist fleet IPs. Atomic `digest.json`.

### 5. Docs

`docs/bobiverse.md` + `bob-irc` skill: shop rooms, pid nicks, no
`!report`, `!bobiverse` is the read. New skill `bob-shop-worker`.

## Acceptance

1. Skills tell a Grok/Cursor MRB agent to JOIN `#<id>` as `w-<short>-<pid>`
   and POST `working_on` — no `!report`.
2. `bobiverse.json` has `reportUrl`.
3. Offline tests for POST merge / delete-worker / shop-down if code lands;
   intake commit may be docs+skills only.
4. PR `work/shop-channel-digest`. Hostile MRB on #124. Bob UAT only.

## Non-goals

Public GET digest. Worker JOIN `#bobiverse`. Productising the listener.
WinRM. Cursor stamping UAT.

## Status

**Intake only** on this commit.
