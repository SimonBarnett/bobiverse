<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: `!bobiverse` must feed the Bob systray

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**Sister (consumer):** https://github.com/SimonBarnett/agentic_build  
`docs/feature-request-bobiverse-digest-feeds-systray-2026-09-21.md`  
**Related:** #36 digest JSON, #46 shop/webhook, agentic_build#26 tray pull, agentic_build#91 cursor pools  
**Raised by:** Simon (Halloy / marchhare talk seat 2026-09-21 ~23:17 BST)  
**UAT + hostile MRB owner:** Bob  

Field kit. Private Ergo. Not a platform.

## Problem

A **bob** (`bob-*` Watch seat) must be able to send `!bobiverse` and receive
**all information required to paint the Bob fleet systray** (`Watch-BobTray` /
`Get-BobTrayHover`).

Today the chair whisper is a **presence digest**: online/offline, shop,
workers, `working_on`. That is not enough for the card:

- Per-machine **Grok weekly %** + **reset / period_end**
- Per-seat **Cursor Models** pool bars (label, %, reset, overage)
- **Job lines**: repo, sha, model, description, run-time (never `?` when known)
- **lastSeen** / idle vs running for tiles

Meanwhile `agentic_build` `Import-BobIrcTrayPull` only ingests whispers that
start with `BOB TRAY v1 …` (kv peer lines). Chair `BOB DIGEST v1` JSON is
not turned into `bob-peers\<id>.json` fields the tray reads. So Watch can
poll `!bobiverse` every ~120s and still leave the systray starved.

## LOCKED

1. **Do not gut the systray.** The card keeps **all data it already shows**
   today (machine tiles, Grok weekly bars + reset, job lines, reach/stale,
   fuels, seat labels, etc.). Do **not** shrink the UI to “whatever the
   thin presence digest has now.”
2. **Only additive UI change:** Cursor usage listed **separately per quota
   pool** (agentic_build#91 — one bar per seat/account). Everything else
   that is already on the card stays.
3. **Refresh path:** tray / Watch refresh calls `!bobiverse` and consumes
   the **JSON** whisper (`BOB DIGEST v1 i/n`). That JSON must carry the
   full tray dataset (not a reduced subset). Optional `BOB TRAY v1` lines
   are fine only if they are equally complete; prefer one documented JSON
   shape.
4. When a **bob-*** asks `!bobiverse`, chair answer is whisper-only (no
   channel JSON dump), covers every registry machine id, no POINT firehose.
5. JSON must be sufficient to rebuild peers for `Get-BobTrayHover` without
   local invent: per machine at least the fields the live card already
   uses (`weekly`, `period_end`/reset, jobs with repo/sha/model/
   description/run_time/state, `lastSeen`, running/queued, online,
   workers/`working_on`, …) plus top-level **`cursor_pools`** (one entry
   per seat).
6. No secrets. No `password=` / report.secret in the digest.
7. Humans may still get the short English brief; bobs must get the full
   machine-readable JSON.

## Gap vs current tree

| Current | Wanted |
|---|---|
| Digest = presence + workers only | Digest JSON = **full systray dataset** |
| Refresh partly local / POINT-era | Refresh = `!bobiverse` JSON pull |
| One collapsed Cursor strip (or incomplete peer pools) | **Separated** Cursor quota bars (#91) + rest unchanged |
| `Import-BobIrcTrayPull` = `BOB TRAY v1` only | Ingest DIGEST JSON → peers (tray-complete) |

## Acceptance

1. `bob-*` `!bobiverse` → JSON includes every field the live TipForm needs
   for all four machines + `cursor_pools`.
2. After one pull, tray paints **no less** than today’s card, plus
   separated Cursor bars; no POINT required.
3. Offline pytest: digest shape + ingest; no live Ergo in pack.
4. PR only; Bob stamps UAT.

## Non-goals

- Stripping tray fields to match today’s thin digest.
- Reintroducing channel POINT firehose.
- HTTP GET of digest.
- Changing Halloy.
