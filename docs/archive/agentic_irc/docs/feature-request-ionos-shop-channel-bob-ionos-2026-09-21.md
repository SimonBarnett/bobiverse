<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-ionos-shop-channel-bob-ionos-2026-09-21.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: `#ionos` shop — `bob-ionos` + all ionos workers

**Date:** 2026-09-21  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/70  
**Raised by:** Simon  
**UAT + hostile MRB owner:** Bob  
**Related:** #46 shop channels, `agentic_build/config/bobiverse.json` (`ionos` →
`bob-ionos`), #56 grok-talk hook (PASS), merged **#68** (Cursor fuel enqueue),
sister [agentic_build#126](https://github.com/SimonBarnett/agentic_build/issues/126)

## Problem

On the **ionos** fleet seat, humans and agents need a dedicated shop room
`#ionos` (machine id `ionos`, not the Windows hostname). **`bob-ionos`**
is the Bob / Grok builder agent for that box. Every **ionos worker**
(`w-io-<pid>`) and **`bob-ionos`** must be present in `#ionos` so shop
traffic, `working_on` lines, and worker conversation stay off `#bobiverse`.

Today `channels_for_nick` already maps `bob-ionos` → `#bobiverse` + `#ionos`
and `w-io-*` → `#ionos` only, but production logs have shown reconnects that
only `JOIN #bobiverse`, and ionos-side worker agents are not always started
with the shop JOIN path.

On the same seat, **grok-talk** (#56) enqueues `grok-inbox.jsonl` only when
peer `weekly` > 0. Ionos often has Grok Build weekly = 0 while **Cursor Models
remaining > 0**; sister Watch-GrokTalk (#126) then has nothing to read and
addressed English stops at `weekly=0 (cannot grok-talk)`. That gap was parked
as #68 and is **in scope here** for `bob-ionos` on ionos (not a second Python
consumer in this repo).

## LOCKED

1. Shop channel name is `#ionos` (machine id `ionos` in `bobiverse.json`).
2. **`bob-ionos`** — ionos Bob/Grok fleet agent — JOINs **`#bobiverse`**
   and **`#ionos`**, stays on both while Watch-Bobiverse runs.
3. **All ionos workers** — IRC nicks `w-io-<pid>` — JOIN **`#ionos` only**
   (never `#bobiverse`). Same rules as #46 for other shops.
4. Do not rename `bob-ionos`. Do not use Libera. Private Ergo
   `irc.ntsa.uk:6697` only.
5. Ergo must allow/register `#ionos` for registered fleet nicks (with
   `#bobiverse`).
6. **Grok-talk fuel (merged #68):** Keep #56 AC2 for **no fuel** — disabled,
   or weekly=0 **and** Cursor Models remaining = 0 → ACK only, no inbox.
   Enqueue when `grok_talk_enabled` / `AGENTIC_IRC_GROK_TALK=1` **and**
   (peer `weekly` > 0 **or** Cursor Models remaining > 0). Use sister
   `remaining_pct`, not display `cursor_label`. When enqueue will fire, ACK
   must **not** say `cannot grok-talk`. No `grok_talk_worker.py` here;
   sister Watch-GrokTalk consumes the inbox. Reply on shop `#ionos` when the
   ask was on `#ionos` (`reply_target`).

## Gap vs current tree

| Area | Now | Want |
|------|-----|------|
| `bobreport.channels_for_nick` | bob-* → fleet + shop | Keep; prove on ionos |
| `irc_agent.py` JOIN | Multi-channel JOIN | Reliable `#ionos` after reconnect |
| `Install-BobIrc` / Watch | Starts `bob-ionos` | Document + verify dual JOIN |
| Worker IRC on ionos | Often no `w-io-*` client | Spawn/join when git worker runs |
| Docs / skills | Shop list includes `#ionos` | State clearly: bob-ionos = ionos grok seat |
| Grok-talk enqueue | `weekly_fuel_ok` only | Also Cursor remaining > 0; ACK text matches gate |
| Envelope / skills | weekly > 0 | Match LOCKED 6; no second consumer |

## MUST

1. After `Install-BobIrc -MachineId ionos` and Watch recycle, Ergo log or
   `irc.log` shows `bob-ionos` **JOIN #bobiverse** and **JOIN #ionos**
   on the same session (no shop-only drift on reconnect).
2. When an ionos git worker runs with IRC worker home under
   `~\.agentic-irc-bobiverse\workers\ionos\<pid>`, that worker’s
   `irc_agent` JOINs **#ionos** as `w-io-<pid>`.
3. Offline pytest: ionos nick table — `bob-ionos` channels include `#ionos`;
   `w-io-4412` channels are `[#ionos]` only.
4. Skills `bob-irc` / `agentic-irc`: one line that **bob-ionos** is the
   ionos Bob/Grok agent and **`#ionos`** is its shop with all `w-io-*`.
5. **Grok-talk (#68):** Enabled + weekly=0 + Cursor remaining > 0 (test
   double) → inbox line; ACK does not say `cannot grok-talk`. Enabled +
   weekly=0 + remaining = 0 → no inbox; non-empty `cursor_label` alone is not
   fuel. Update `docs/grok-talk-envelope-v1.md` to match.

## MUST NOT

- Move fleet POINT/ACTION firehose into `#ionos`.
- Join workers to `#bobiverse`.
- Break other shops (`#flamingo`, `#marchhare`, `#ce-priority-dev1`).
- Add `grok_talk_worker.py` or any in-repo grok.exe / cursor-agent consumer.
- Treat tray `cursor_label` (`-£75`, etc.) as fuel.

## Acceptance

1. Halloy (or log): `NAMES #ionos` lists `bob-ionos` and each live
   `w-io-*` for jobs on ionos.
2. `pytest -q` includes ionos shop JOIN/channel tests (extend
   `test_bobiverse_talk` or `test_bobreport`).
3. House-clean doc cross-link in `agentic_build/docs/bobiverse.md` shop
   table (sister note only; no UAT stamp in this FR).
4. Pytest: grok-talk AC1–AC3 from merged #68 (disabled / protocol / `bob-*` /
   `!bobiverse` never enqueue).

## Out of scope

- Sister Watch `reportUrl` (#124 on agentic_build).
- Replacing sister Watch-GrokTalk / BobBridge worker; LLM inside
  `Watch-Bobiverse` or the ACK hot path.
