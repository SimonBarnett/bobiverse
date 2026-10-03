<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-report-bobiverse-digest-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: !report ingest + !bobiverse JSON digest

**Superseded write path:** `#36` `!report` ingest is **scrubbed**. Live write is
`POST reportUrl` / JOIN/QUIT. Live read is still `!bobiverse` (see
`docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md`, issue #46).

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/36
**Producer (sister):** https://github.com/SimonBarnett/agentic_build (`Watch-Bobiverse`, `Write-BobIrcStatus`)
**Raised by:** Simon (Halloy `#bobiverse` screenshot 2026-09-21 ~09:52–09:55 BST)
**UAT + hostile MRB owner:** Bob
**Related:** #6 / #9 quiet-talk DMs, #26 channel-talk + tray pull, #34 house-clean, agentic_build#36 / #89

Field kit. Private Ergo `irc.ntsa.uk:6697` `#bobiverse` only. Not a platform.

## Problem

The channel is still a telemetry dump. Halloy shows six nicks
(`bob`, `bob-dev1`, `bob-flamingo`, `bob-ionos`, `bob-marchhare`, `simon`)
and a wall of:

```text
bob-dev1 MOOT v1 POINT … :BOB v1 id=ce-priority-dev1 weekly=8 reset=… cur=-£75.03 …
bob-marchhare MOOT v1 POINT … :BOB v1 id=marchhare weekly=4 …
bob-flamingo MOOT v1 POINT … :BOB v1 id=flamingo weekly=8 …
```

Same blob every ~30s. `lastSeen` ticks. `jobs=-`. Humans cannot talk.
Quiet-talk (#6) and tray-pull (#26) did not kill the producer POINT.

Need a **write command** bots use on change, a **digest** the briefer
holds, and a **read command** that returns that digest as JSON. No
firehose.

## LOCKED

1. **Bots do not POINT `BOB v1` to `#bobiverse` every Watch tick.**
   Disk `bob-peers\<id>.json` may still be written locally. The channel
   does not get the kv line.
2. **Write path is `!report`.** First token, case-insensitive.
   Accepted in `#bobiverse` or as PM to a `bob-*`. One briefer ingests
   (chair `bob-*`, else first roster `bob-*`). Other `bob-*` nicks do
   not ACK and do not re-broadcast.
3. **Raw `!report` is not echoed back to the channel.** Ingest updates
   the digest. Optional: one short English line on `TASK START` /
   `TASK STOP` only (not on `PCENT`, not on `UPTIME` heartbeat).
4. **Read path is `!bobiverse`.** Returns the **latest digest as JSON**
   to the **asker only** (PRIVMSG nick / whisper). Do not dump the JSON
   onto `#bobiverse`. Per-nick cooldown (~60s human, ~120s agent).
   One briefer answers.
5. **`!report ?`** (also `!report help`) whispers the help text to the
   asker. Not a channel novel.
6. **No secrets.** Refuse lines that look like `password=` / `XAI_API_KEY=`
   assignments. Do not put connect.password in JSON.
7. Git-task verbs stay `SPEC WAIT BUILD PUSH MRB FIX UAT`. `!report` is
   status ingest, not a new git verb family.

## Command surface

```text
!report TASK START {repo} {sha} {model} {task-description} {run-time}
!report TASK STOP  {repo} {sha} {model} {task-description} {run-time}
!report PCENT {machinename} {Source} {xx%}
!report UPTIME {since}
!report ?
```

`{task-description}` may be several tokens; `{run-time}` is the last
token. `{sha}` is hex (7+ chars) or `-` if none. `{repo}` is `owner/name`
or a short repo name already used on the box. `{Source}` is a fuel/
meter id (`cursor-models`, `grok-build`, `grok-bot`, `copilot`, …) not
a vendor essay. `{xx%}` is an integer 0–100 plus optional `%`.
`{since}` is ISO date or ISO datetime (`2026-09-20` or `2026-09-20T08:00:00Z`).

Malformed `!report`: whisper one line `ERR report …` to the sender.
Do not speak on the channel.

### Digest JSON (`!bobiverse` body)

One object, one line if it fits under ~350 chars after compacting;
otherwise split as `BOB DIGEST v1 i/n` lines to the asker only (same
chunk style as SEAL, but this payload is **not** a secret).

```json
{
  "v": 1,
  "ts": "2026-09-21T09:55:00Z",
  "briefer": "bob-ionos",
  "machines": {
    "flamingo": {
      "nick": "bob-flamingo",
      "uptime_since": "2026-09-20T00:00:00Z",
      "pcent": { "cursor-models": 12, "grok-build": 8 },
      "task": {
        "state": "START",
        "repo": "SimonBarnett/agentic_build",
        "sha": "8d9a852",
        "model": "composer-2.5",
        "description": "house-clean docs",
        "run_time": "12m"
      }
    }
  }
}
```

Unknown machine ids are ignored (same rule as POINT: `NOPE` dropped).
Ids are lowercase `[a-z0-9-]`. Alias `dev1` / `ce-priority-dev1` /
nick `bob-dev1` is one machine.

`PCENT` updates only that source on that machine. `UPTIME` sets
`uptime_since` for the **sender's** machine unless `{machinename}` is
later added; v1 form is `!report UPTIME {since}` scoped to the sending
nick's machine.

`TASK STOP` with no live task: still record last task + `state=STOP`.

## Producer (agentic_build) — required sister work

Watch / `Write-BobIrcStatus` must:

1. Stop appending `MOOT v1 POINT` / `BOB v1` to the channel outbox on
   idle ticks.
2. On job start / stop: send `!report TASK START|STOP …` (PM to briefer
   preferred; channel allowed if PM not wired yet).
3. On meter change of ≥1 percentage point: `!report PCENT …`.
   Do not PCENT every 30s when the number is unchanged.
4. Once per process start (not per tick): `!report UPTIME {iso}`.
5. Tray still reads `bob-peers\`. After this FR, tray may also parse
   `!bobiverse` JSON (agent poll ~120s) per #26. Do not require both
   on day one if disk still works; do not leave POINT on the channel
   as the compatibility path.

If the producer cannot land in the same sprint, irc still accepts
`!report` / serves JSON so a manual Halloy test works.

## Help text (`!report ?`)

Whisper, keep short:

```text
!report TASK START|STOP <repo> <sha> <model> <desc> <runtime>
!report PCENT <machine> <source> <n%>
!report UPTIME <since-iso>
!bobiverse  → JSON digest (whisper)
```

## Acceptance

1. Offline pytest: parse the four `!report` forms; reject secrets;
   reject bad machine id; `?` returns help string; digest JSON round-trips.
2. Two `TASK START` then `PCENT` then `!bobiverse` fixture → JSON has
   both machines' pcent and the live task. No channel-echo flag set.
3. Duplicate `PCENT` with same `xx` does not mark "speak".
4. `!bobiverse` formatter emits JSON only (not `BOB v1` kv, not a
   Halloy novel on the channel).
5. Skill `bob-irc` documents: no POINT firehose; write `!report`;
   read `!bobiverse` JSON whisper.
6. Commit + PR. Hostile MRB on #36. Only Bob stamps UAT.

## Non-goals

- Changing Ergo flood limits.
- SEAL wrapping the digest (not a secret).
- DUMB / Mode 3 / Libera.
- Replacing the tray chrome.
- Productising a public status API.
- Letting Cursor stamp UAT via `!report`.
