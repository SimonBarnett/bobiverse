<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bob-grok-irc-listen-talk-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: Grok-talk on IRC (LLM listen + reply)

**Date:** 2026-09-21
**Repo:** https://github.com/SimonBarnett/agentic_irc
**Sister:** https://github.com/SimonBarnett/agentic_build (fuel picker, `Start-BobWorker` / Grok Bot bridge, tray weekly gate)
**Raised by:** Simon (ionos UAT: `ping bob-ionos` silent until manual `outbox.txt`; Cursor session not on wire)
**Related:** agentic_irc#53 / PR #54 (mention **ACK** without grok.exe — merged `58daf8a`),
#46 shop channels, #26 channel-talk, flamingo ad-hoc listen-talk (not in tree on every seat)
**UAT + hostile MRB owner:** Bob

## Problem

After shop #51 and listen/ACK #54, `bob-ionos` still does **not** hold a
conversation on `#bobiverse`:

- Plain English (`ping bob-ionos`, `@bob-ionos …`) is ignored on boxes that
  have not recycled `irc_agent` after #54, and even with #54 only yields a
  **canned ACK** (`weekly=0 (cannot grok-talk)` when Grok Build weekly is
  empty).
- This **Cursor / Grok IDE session** is not attached to IRC; only
  `outbox.txt` → `irc_agent.say()` can post (proved manually on ionos).
- `Watch-Bobiverse` must stay **no grok.exe** (#53 LOCKED). Reasoning belongs
  in a **separate** short-lived worker, not the 30s poll loop.
- flamingo’s richer `@cursor-flamingo` replies are **local Grok/listen-talk**
  automation, not shipped for ionos / marchhare / dev1.

Simon wants **listen + talk**: addressed lines on IRC should reach an agent
that can answer in English on-channel or in Query, within fuel rules.

## LOCKED

1. **Layering:** Keep #54 ACK path (no LLM). Add an **optional** grok-talk
   path when fuel allows (Grok Build weekly > 0, or Grok Bot desktop, or
   Cursor Models per `Select-BobGitWorker` — product choice in sister build
   repo; IRC side only defines the **hook** and wire format).
2. **Trigger:** Same addressing rules as #54 (`addressed_to`, not protocol
   lines, not `bob-*` askers, ~20s cooldown per asker) **plus** a machine
   config flag `grok_talk_enabled` default **false** until UAT (or env
   `AGENTIC_IRC_GROK_TALK=1` on seats that opt in).
3. **Watch stays dumb.** `irc_agent` (or a sibling `irc_grok_bridge.py`
   started by Install-BobIrc) enqueues work; it does not import grok.exe in
   the hot ACK loop.
4. **Reply surface:** One or more PRIVMSG lines, **one fact per line**, channel
   if the ask was on `#bobiverse` / shop; Query if the ask was PM. Cap 350
   chars per line (reuse #54). No POINT firehose. No secrets on wire
   (`looks_like_secret` on outbound).
5. **weekly=0:** ACK still works (#54). Grok-talk path **does not** start;
   ACK line may say `cannot grok-talk` (already does).
6. **No `!report` write.** `!bobiverse` stays briefer/digest (whisper). This
   FR is **conversational** traffic only.
7. Offline pytest with a fake enqueue backend (no live Ergo, no live grok in
   CI). PR only. Only Bob stamps UAT.

## UNKNOWN

- Exact enqueue API: append `grok-inbox.jsonl` vs BobBridge `Start-BobWorker`
  with `reply_channel=irc-outbox` vs Grok Bot named agent on box.
- Whether grok-talk replies on **shop** `#ionos` or only `#bobiverse`.
- Max concurrent grok-talk jobs per machine (1 recommended).
- Cursor Models on ionos when weekly bar is 0% but on-demand — sister build
  policy, not IRC protocol.

## Gap vs tree (`58daf8a`)

| Current | Wanted |
|---|---|
| `_maybe_mention_reply` → canned `mention_reply_line` | Same trigger; optional second path → enqueue LLM |
| No inbox from IRC to Grok | Structured job: `{asker, channel, body, nick, machine_id}` |
| Manual `outbox.txt` for human-visible send | Worker completion appends English lines to outbox (existing drain) |
| flamingo-only listen-talk | Repeatable install on all `bob-*` seats |

## Acceptance

- **AC1** With `grok_talk_enabled` and a test double worker, an addressed
  channel line produces ≥1 outbound PRIVMSG derived from worker stdout (not
  the canned ACK-only template).
- **AC2** With grok-talk disabled or weekly=0, behavior matches #54 (ACK only).
- **AC3** Protocol / `bob-*` / `!bobiverse` lines never enqueue grok-talk.
- **AC4** Pytest green; no `password=` / `XAI_API_KEY=` assignments in repo.

## Non-goals

- Replacing `!bobiverse` digest or shop POST callback (#46 / #124).
- LLM inside `Watch-Bobiverse.ps1`.
- Halloy theme / Simon’s client config.
- MRB PDF.
