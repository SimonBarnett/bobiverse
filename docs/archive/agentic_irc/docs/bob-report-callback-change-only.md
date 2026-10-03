<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/bob-report-callback-change-only.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# POST /bob/v1/report — change-only merge (issue #73)

Write-only callback on ionos (`scripts/bobcallback.py`). **No HTTP GET** of digest.
Live URLs on the same listener:

- Fleet digest: `http://irc.ntsa.uk:80/bob/v1/report`
- GitHub webhooks: `http://irc.ntsa.uk:80/bob/v1/git`

## Auth

- Header `X-Bob-Secret` (env `BOB_REPORT_SECRET` or `~\.grok\bob\report.secret`)
- Allowlisted peer IPs (`BOB_REPORT_ALLOW`, default loopback)

## Body

JSON object. Required for fleet merge:

| Field | Notes |
|-------|--------|
| `op` | `merge`, `delete-worker`, or `shop-down` |
| `machine` / `id` | Registry machine id (`ionos`, `flamingo`, …) |

**Merge deltas** (include only fields that changed):

- Create a worker first: `pid`, `nick`, `kind`, `state` — **no**
  `working_on`. Then a second merge may set `working_on` or idle.
- `online`, `status`, `working_on`, `pid`, `kind`, `state`, `nick`
- `pcent` (fuel / weekly buckets), `uptime_since`
- Optional peer fields when present: `weekly`, `cursor_label`, `jobs`, `repo`, `sha`, `model`, `fuel`

**Do not POST** heartbeat-only updates (`lastSeen`, `ts`, bare polls). The server compares canonical machine state; identical merges return **HTTP 200** with an empty body and do not rewrite `digest.json`. First change returns **204**.

## Consumer

- `digest.json` at `~\.agentic-irc-bobiverse\digest.json`
- Digest **chair** (`AGENTIC_IRC_CHAIR_NICK` / `chairNick` in digest) answers `!bobiverse` via whisper only
- `bob-<machine>` builders do not PRIVMSG fleet status or `BOB DIGEST` to `#bobiverse`

## Producer

See agentic_build #124 — `Write-BobIrcStatus` should hash the peer blob and skip POST when only `lastSeen` advances.

## GitHub (`POST /bob/v1/git`)

GitHub (or compatible) delivery. Does **not** merge `digest.json` and does
**not** use `X-Bob-Secret`.

- Same IP allowlist as fleet (`BOB_REPORT_ALLOW`, default loopback).
- Header `X-GitHub-Event` (GitHub delivery) is required.
- JSON body per GitHub webhook shape. The listener appends
  `PRIVMSG #bobiverse :GIT …` to `chair-outbox.txt` on
  `BOB_DIGEST_HOME` (`~\.agentic-irc-bobiverse`).
- Jeeves (`irc_agent.py --chair`) is the only nick that drains that file.
  `--home` / `AGENTIC_IRC_HOME` is `~\.agentic-irc-jeeves`.
  `scripts/Install-BobChair.ps1` sets both. Do not point `--home` at the
  `bob-ionos` home. Without `BOB_DIGEST_HOME`, GIT lines stay stuck.
- Talk seats do not narrate these events.

Returns **204** when the announce is queued. **400** on missing event, bad
JSON, or a queue write failure. No HMAC verification in-tree (operator
network posture only).

## GIT claim (`POST /bob/v1/report` `op=git-claim`)

Secret required (`X-Bob-Secret`), same as other report writes.

```json
{"op":"git-claim","nick":"w-fl-4412","channel":"#flamingo"}
```

**200** body `{"ok":true,"claimed":{repo,task,id,…}}` moves the oldest
unaccepted row to `accepted` in that same write. **200**
`{"ok":true,"claimed":null}` means the queue was empty. Jeeves calls this
when a shop `w-*` sends `!BORED` and then says `{repo} {task} {id}` once.
`!ACCEPT` does not claim.

After that line the worker POSTs `op=merge` with `working_on` (and `agent`
/ `model` when known). `state=idle` clears `working_on`, `agent`, and
`model`.
