<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-shop-channel-worker-cc-webhook-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: per-machine shop channels + worker CC + write-only digest callback

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_irc
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/46
**Sister:** https://github.com/SimonBarnett/agentic_build/issues/124
**Raised by:** Simon
**UAT + hostile MRB owner:** Bob
**Build orchestrator:** Bob — `Start-BobBuild -Task git`
**Related:** #6 / #9 quiet-talk, #26 channel-talk + tray pull, #34 house-clean,
#36 `!report` digest (this FR **scrubs** `!report`)

Field kit. Private Ergo `irc.ntsa.uk:6697`. Peer mesh of `bob-*` boxes.
Not a platform. Digest is **not** an HTTP resource.

## Problem

`#bobiverse` is the only room. Humans cannot see which box a Grok/Cursor
MRB/build is on, which worker on that box is talking, or **what that
worker is working on** in one English sentence.

Thinking traces and tool transcripts stay trapped in the IDE unless a
human has opened a Query with that worker.

`!report` (#36) is a second line protocol on top of JSON. It is
redundant once peers can POST a write-only callback and the briefer
already sees JOIN/QUIT. Keep one IRC read: `!bobiverse`.

## LOCKED

1. Ids stay in `agentic_build/config/bobiverse.json`:
   `flamingo`, `marchhare`, `ionos`, `ce-priority-dev1`.
   Alias `dev1` / `ce-priority-dev1` / nick `bob-dev1` is one machine.
   Shop channel is `#<machine-id>` (`#dev1` = `#ce-priority-dev1`).
   Do not name channels after Windows hostnames.

2. Worker JOINs `#<machine-id>` only. Never `#bobiverse`.
   Local `bob-<id>` is in both `#bobiverse` and the shop. Bob is the
   only shop→fleet bridge.

3. Shop gets conversation stdout only (visible assistant text) plus
   `working_on` change lines.

4. Thinking traces + tool transcripts go to a worker Query **only
   while that PM is open**. No PM → traces stay off IRC.

5. **Job description is first-class.** Every running worker has
   `working_on` — “This is what I’m working on.” Set at start,
   updated when the task text changes, cleared when the worker is
   deleted.

6. **Digest is not public.**
   - No `GET /digest`. No HTTP read. No tray URL fetch of the file.
   - File lives only on the briefer box:
     `~\.agentic-irc-bobiverse\digest.json`
   - **Read path:** IRC user says `!bobiverse` → briefer whispers JSON.
   - **Write path:** `POST` callback on ionos, and/or IRC disconnect /
     JOIN the briefer already sees.

7. Callback is **write-only**, on ionos, peer-reachable (IONOS panel
   allowlist of flamingo / marchhare / DEV1 / ionos + header
   `X-Bob-Secret`). Secret is never a JSON field and never IRC.

8. `#bobiverse` gets Bob `/me` lifecycle + “working on …” on change.
   No stdout. No traces.

9. Secret-shaped lines (`password=` / `XAI_API_KEY=` /
   `connect.password` / live PIN / PSK) dropped everywhere.

10. **Identity is machine + pid.** Unique worker key
    `<machine-id>:<pid>`. IRC nick `w-<shortid>-<pid>`.

11. **Worker disconnect deletes the worker object.** Assumed dead
    until a new START/JOIN recreates `workers.<pid>`.

12. **Bob disconnect persists the machine as offline**
    (`status="I am offline"`) and **closes the shop channel**.
    All workers on that box PART/QUIT; their digest keys are deleted.
    The machine seat remains in the digest so `!bobiverse` still lists it.

13. **`!report` is scrubbed.** Old verbs are not ingested.
    Whisper once `ERR report gone — use callback or !bobiverse`.

14. Pytest offline. Only Bob stamps UAT. Git verbs stay
    `SPEC WAIT BUILD PUSH MRB FIX UAT`.

## Surfaces

| Surface | Direction | Content |
|---|---|---|
| `#<machine-id>` | worker → shop | Conversation stdout + `working_on` updates |
| Query with worker | if PM open | Conversation + thinking + tool transcripts |
| Query with `bob-<id>` | in | Box answer (`!bobiverse` / last ACTION), not child traces |
| `#bobiverse` | Bob ACTION | `/me` lifecycle + working-on |
| `POST …/bob/v1/report` | peers → ionos | Write-only merge |
| `GET` any digest URL | — | **Does not exist** |
| `!bobiverse` | IRC → briefer | **Only** read of the digest |

## Identity

Unique worker key = `<machine-id>:<pid>`
Example: `flamingo:4412`

- `pid` is the OS process id of that Grok/Cursor MRB/build agent.
- Kind (`grok` / `cursor`) is metadata, not the key.
- After delete, a later OS reuse of the same pid is a **new** life
  (`started` now).

### IRC nick

```
w-<shortid>-<pid>
```

| machine-id | shortid | nick example | shop |
|---|---|---|---|
| flamingo | fl | `w-fl-4412` | `#flamingo` |
| marchhare | mh | `w-mh-2201` | `#marchhare` |
| ionos | io | `w-io-884` | `#ionos` |
| ce-priority-dev1 | d1 | `w-d1-1024` | `#ce-priority-dev1` |

433: one `_` suffix (`w-fl-4412_`). Digest still keys `flamingo:4412`.

`--home`: `~\.agentic-irc-bobiverse\workers\<machine-id>\<pid>`

## Persistence

| Object | Disconnect | Digest |
|---|---|---|
| Machine (`bob-<id>`) | Shop `#<id>` closed; workers PART/killed | **Seat remains.** `online=false`, `working_on=""`, `workers={}`, `status="I am offline"` |
| Worker (`w-<shortid>-<pid>`) | That pid only | **Delete** the worker key. No OFF stub. |

Machine reappear: `bob-<id>` JOINs `#bobiverse` **and** recreates
`#<id>` → `online=true`, `status="I am online"`, `working_on` empty
until a worker START.

Worker reappear: new pid object only. Nothing to revive.

A worker disconnect does **not** close `#<id>` while Bob is present.

## Bob disconnect tears down the shop

On QUIT / ERROR / PING / local death of `bob-<id>`:

1. Every remaining `w-<shortid>-<pid>` on that box PARTs `#<id>`
   (then QUIT IRC if that was their only channel).
2. Watch on that box kills leftover worker `irc_agent` processes.
3. Empty channel is left for Ergo to drop. No ChanServ product.
4. Digest: delete all `machines.<id>.workers.*`. Machine seat stays.
5. One ACTION: `/me lost bob-flamingo — #flamingo closed`
6. Open human Queries may get one line `shop closed`, then no more
   shop PRIVMSG.

Do not re-JOIN the shop until `bob-<id>` is back.

## Job description (“This is what I’m working on”)

On worker start the skill MUST set `working_on` before the first
shop line.

Shop announcement (change only):

```
w-fl-4412: This is what I'm working on: agentic_irc shop-channel FR (BUILD)
```

Bob ACTION:

```
/me 's pid 4412 on flamingo is working on agentic_irc shop-channel FR
/me 's MRB job finished successfully on flamingo
/me sees w-fl-4412 drop from #flamingo (pid 4412)
/me lost bob-ionos — #ionos closed
```

Cooldown: one ACTION per worker per event class per 30s.
`working_on` required at START. Empty string is idle.

## CC rules

```
working_on change     → shop + ACTION (change only)
visible assistant     → shop; Query if open
thinking / tool xscr  → Query only, while PM open
secrets-shaped        → drop
```

“PM is open” = this process has received a PRIVMSG from that nick
in this session (optional idle timeout; next human line re-opens).
Flood 0.8s. Split ~350 chars. Drop empty.

Workers never JOIN `#bobiverse`. Bob never copies shop stdout or
traces onto `#bobiverse`.

## `!bobiverse` (only IRC command)

First token, case-insensitive. Channel or PM.

**One briefer answers** (chair `bob-*`, else first **online**
`bob-*`). Whisper to the **asker only**. Cooldown ~60s human /
~120s agent.

```text
!bobiverse
!bobiverse ?
!bobiverse <machine-id>
```

| Form | Reply (whisper) |
|---|---|
| `!bobiverse` | Full digest JSON (every registry seat; offline included; no dead pids) |
| `!bobiverse ?` | Help text |
| `!bobiverse flamingo` | That machine object only. Unknown id → `ERR no such machine` |

Do not dump JSON onto `#bobiverse`. Do not POINT.

Help whisper:

```text
!bobiverse          JSON digest (whisper)
!bobiverse <id>     one machine
!bobiverse ?        this text
write: POST reportUrl (no !report)
```

Optional one English line **before** the JSON, whisper-only:

```text
flamingo: working on agentic_irc shop-channel FR (pid 4412)
ionos: I am offline
marchhare: I am online (idle)
```

If JSON exceeds ~350 chars, split `BOB DIGEST v1 i/n` to the asker
only (not a secret).

### Scrub `!report`

`!report` / `!report ?` / `TASK START|STOP` / `PCENT` / `UPTIME`
are removed from skills, briefer, and #36 docs.

Writes are only:

1. `POST /bob/v1/report` (ionos, write-only)
2. IRC events the briefer sees (JOIN, QUIT, ERROR, shop PART,
   Bob drop → shop down)

Old `!report` in channel or PM: whisper once
`ERR report gone — use callback or !bobiverse`. Do not ingest.

## Write-only callback (ionos)

`POST /bob/v1/report` only.

- 204 on merge, 400 malformed, 401 missing/bad secret, 403 IP.
- **No GET, no HEAD, no listing.**
- Peer-reachable on ionos. Port + URL in
  `agentic_build/config/bobiverse.json` as `reportUrl`.
- Allowlist flamingo / marchhare / DEV1 / ionos.
- Secret file `~\.grok\bob\report.secret` (env `BOB_REPORT_SECRET`).
- Atomic write `digest.json` on the briefer box.
- Watch POSTs `pcent` / `uptime_since` / `working_on` on change.

Disconnect the briefer **already saw** does not need a POST.
Local process death the server never saw: Watch POSTs a delete
for that pid (or shop-down if Bob died). Dedupe
`(machine, pid, DISCONNECT)` for ~30s.

## JSON

See the intake file examples in this document's source: machines persist
with `status` `I am online` / `I am offline`; workers keyed by pid string;
`events` last ~20; traces never stored.

### POST ops

- `op: merge` — patch machine/worker/`working_on`
- `op: delete-worker` — remove `workers.<pid>`
- `op: shop-down` — Bob gone; empty workers; `online=false`

Secret is header `X-Bob-Secret`, not a JSON field.

Full example objects live in this FR under the conversation lock;
implementers copy the schema from issue #46 body + this file as landed
on `work/shop-channel-digest`.

Machine object required fields: `id`, `nick`, `shop`, `online`,
`status`, `working_on`, `workers`.
Worker object required fields: `pid`, `key`, `nick`, `kind`, `state`,
`working_on`.

## Ask (this repo)

1. Briefer: parse worker nicks; on QUIT delete pid; on `bob-*` QUIT
   mark machine offline + shop-down; serve `!bobiverse`.
2. `irc_agent` / Watch contract: `bob-*` JOINs `#bobiverse` and
   `#<id>`; workers JOIN `#<id>` only.
3. Digest merge into `digest.json`. Remove `!report` parsers.
4. Skills `bob-irc` + `agentic-irc`: shop names, pid nicks, CC rules,
   no `!report`.
5. Offline pytest for nick helper, delete-on-QUIT, persist-offline,
   `!bobiverse` forms, secret drop, no GET handler.

## Acceptance

1. Offline: shop name + nick helpers; `working_on` on START; traces
   gated on `pm_open`; worker QUIT deletes pid; Bob QUIT sets
   `I am offline` and empties workers; `!bobiverse` lists offline
   seats; `!report` not ingested.
2. Two workers on one fixture machine → two nicks, one shop; Bob
   ACTIONS only on `#bobiverse`.
3. HTTP test client can POST; GET is 404/405 (listener may live on
   sister repo).
4. Skills match LOCKED. No secrets. PR on `work/shop-channel-digest`.
   Hostile MRB on #46. Only Bob stamps UAT.

## Non-goals

- Public digest URL / GET / CDN / tray HTTP pull of JSON.
- Traces on shop or `#bobiverse`.
- Worker JOIN `#bobiverse`.
- Unauthenticated callback.
- ChanServ product, DUMB as git worker, WinRM, SEAL v2, tray chrome.
- Letting Cursor stamp UAT.

## Status

**Intake only** — no runtime code in the intake commit.
Supersedes the `!report` write path in
`docs/feature-request-report-bobiverse-digest-2026-09-21.md` (#36).
`!bobiverse` as whisper-JSON reader stays; its payload becomes this
digest.
