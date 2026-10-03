<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-digest-webhook-chair-change-only-2026-09-21.md, last changed 2026-09-24. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: change-only webhook digest + built-in chair (no channel status spam)

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/73  
**Raised by:** Simon (Halloy / `#bobiverse` transcript — `bob-ionos` status wall)  
**UAT + hostile MRB owner:** Bob  
**Sister (producer):** https://github.com/SimonBarnett/agentic_build/issues/124 and `Watch-Bobiverse` / `Write-BobIrcStatus`  
**Related:** #46 shop + `POST /bob/v1/report`, #26 channel-talk (amend), #36 digest read (`!bobiverse`), #70 `#ionos` shop

## Problem

Humans see the wrong surface as **“bob ionos”** and a wall of **`bob-ionos`**
PRIVMSG that is not shop conversation, for example:

- `Working on ?.`
- `dev1 is on grok.exe now.` / `ionos is on Cursor Models now.`
- `flamingo: I am offline` … per-machine lines every poll
- `BOB DIGEST v1 1/2` / `2/2` JSON chunks on the **channel** (must be
  **whisper to asker only**)

That is fleet telemetry, not chat. It fires on a timer (~30–120s) even when
nothing meaningful changed. Simon wants:

1. **Write path:** peers POST to a **webhook** on ionos that **merges**
   `digest.json` — **only when state changes** (compare to last sent snapshot /
   last login / fuel / online / `working_on` / jobs — not bare `lastSeen` ticks).
2. **Read path:** a **built-in chair IRC identity** that **only handles
   commands** (`!bobiverse`, help) by reading `digest.json` — no Watch-driven
   status narration on `#bobiverse` or `#ionos`.
3. **`bob-ionos`** stays the ionos Bob/Grok **builder** seat (#70); it is not
   the channel announcer for the whole fleet.

## LOCKED

1. **No periodic fleet status on IRC channels.** No `BOB v1` POINT firehose.
   No repeating English “I am online/offline” lines for remote machines on
   `#bobiverse`. No `BOB DIGEST` on a channel — whisper to asker only.
2. **Digest file** on the briefer box:
   `~\.agentic-irc-bobiverse\digest.json` (same as #46). Still **no HTTP GET**
   of digest for humans; `!bobiverse` whispers JSON.
3. **Write-only webhook** on ionos: extend `POST /bob/v1/report` (or documented
   sibling path) with a **change-only** contract — body rejected or no-op if
   payload is identical to last merged state for that machine id (server may
   compare canonical JSON; client must not POST heartbeat-only `lastSeen`).
4. **Built-in chair user:** one registered Ergo identity (config:
   `agentic_build/config/bobiverse.json` — `chairNick: Jeeves`; `--home`
   `~\.agentic-irc-jeeves`; digest files on `BOB_DIGEST_HOME`
   `~\.agentic-irc-bobiverse`; do not share the bob-ionos `--home`; MOOT
   chair is a different seat) running a **slim seat** that:
   - JOINs `#bobiverse` (and does not narrate fleet status into channel)
   - Ingests webhook merges into `digest.json` (briefer role)
   - Answers `!bobiverse` / `!bobiverse ?` / `!bobiverse <id>` via **whisper**
   only
   - Does **not** run grok.exe / Cursor / Watch tray talk lines
5. **Shop channels** (`#ionos`, …): worker stdout + `working_on` only (#46).
   Fleet digest never copied to shop.
6. Secrets: `X-Bob-Secret` header only; never IRC; `looks_like_secret` on out.

## Gap vs current tree

| Area | Now | Want |
|------|-----|------|
| `Write-BobIrcStatus` / Watch | English + digest chunks to `outbox` → channel | POST webhook on **delta** only; no channel status |
| `bob-ionos` | Briefer + talks fleet in channel | Builder on ionos; chair handles digest commands |
| `bobcallback` | POST merge exists | Document change-only + idempotent merge |
| `!bobiverse` | Briefer on first `bob-*` | Dedicated **chair** nick is sole digest responder |
| Halloy UX | Looks like “bob ionos” telemetry room | `#bobiverse` = humans + chair commands; `#ionos` = ionos shop |

## MUST

1. **Producer (agentic_build):** before POST, compute diff vs last successful
   POST (or last `bob-peers\<id>.json` export). Skip POST when only `lastSeen`
   advanced. Include fields: `online`, `status`, `weekly`/`cursor_label`, `jobs`,
   `working_on`, `repo`/`sha`/`model`/`fuel` when present.
2. **Consumer (agentic_irc):** `apply_callback` / webhook handler returns 204
   on merge; 200/204 on no-op duplicate; never PRIVMSG digest to channel.
3. **Chair seat:** `Install-BobIrc` or new `Install-BobChair.ps1` starts chair
   agent on ionos; MOOT chair semantics unchanged for floor control.
4. **Tests:** pytest — duplicate POST does not change digest twice; `!bobiverse`
   whisper only; channel outbox never contains `BOB DIGEST` PRIVMSG to
   `#bobiverse`.
5. **Docs/skills:** `bob-irc`, `agentic_build/docs/bobiverse.md` — chair vs
   `bob-<machine>` builder split.

## MUST NOT

- Revive `!report` ingest (#46 scrub).
- HTTP GET digest URL.
- Move thinking traces to `#bobiverse`.
- Require Halloy in CI.

## Acceptance

1. With Watch running on two boxes, `#bobiverse` does **not** gain a new line
   every 30s when fleet is idle; webhook POST count stays flat.
2. On fuel change (e.g. ionos Cursor Models), **one** POST updates digest; optional **one** short English line only if #26 change-talk still desired (default **off** for this FR).
3. Human `!bobiverse` in `#bobiverse` gets JSON whisper from **chair** nick, not from `bob-ionos`.
4. `pytest -q` green for new tests.

## Out of scope

- Tray card layout (agentic_build #91 / #100).
- Grok-talk inbox (#56 / PR #67).
- Ergo TLS / firewall (docs only).
