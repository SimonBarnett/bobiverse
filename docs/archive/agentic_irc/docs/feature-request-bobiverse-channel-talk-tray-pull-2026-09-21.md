<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-bobiverse-channel-talk-tray-pull-2026-09-21.md, last changed 2026-09-21. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: channel talk + !bobiverse tray pull

**Date:** 2026-09-21
**Repos:**
- Protocol: https://github.com/SimonBarnett/agentic_irc
- Producer / tray: https://github.com/SimonBarnett/agentic_build
**Raised by:** Simon (UAT of MRB PASS-nits #9 / FR #6)
**Related:** agentic_irc#6 / #9 (quiet talk DMs — wrong surface for humans),
agentic_build#36 (producer quiet talk, still open)

## Problem

After #6 / PR #7, `!bobiverse` answers as **whispers** (Halloy Query tab).
Simon: that is wrong. Conversational status lines belong in the **channel
chat** (`#bobiverse`). Agents (not humans) should call `!bobiverse` about
every **two minutes** to refresh the **system tray** from each peer's last
update.

Also: **ionos never turns up** cleanly — peer JSON shows `jobs[].repo` as
`?`, so talk lines say `Working on ?.`. Tray / network picture skips or
mis-labels ionos.

## LOCKED

1. **Human-readable status goes in `#bobiverse` (channel PRIVMSG),** one
   fact per line, only on a real field change or a one-shot long-running
   warning. Not a whisper/Query dump of the whole fleet for humans.
2. **`!bobiverse` is an agent/tray pull.** Any fleet agent (or Watch) may
   send `!bobiverse` about every **120 seconds** (jitter OK). The briefer
   answers with the **last update from each** machine so the asker can
   write `bob-peers\<id>.json` / tray state. Do not require humans to open
   Query to see status.
3. **Do not** PRIVMSG a full `BOB v1` POINT blob every Watch tick for human
   ears. Tray JSON on disk stays populated.
4. **Ionos must appear** in the network picture and tray with a real repo /
   idle line — never `Working on ?.` when a job is known; never omit ionos
   when the nick is joined and Watch is alive.
5. One briefer answers `!bobiverse` (chair if `bob-*`, else first roster
   `bob-*`). Channel does not get a second copy of the tray pull payload
   if the pull dialect is not human chat (see UNKNOWN).
6. No secrets. No `password=` / `XAI_API_KEY=` in git or prompts.

## UNKNOWN

- Exact on-wire shape of the tray-pull answer (conversational lines vs a
  compact machine-readable dialect agents parse). Prefer something Watch /
  tray can ingest without an LLM; keep one fact per PRIVMSG if English.
- Whether human `!bobiverse` in channel still gets a short English summary
  in-channel (recommended yes) while agents prefer a parseable form.
- Who posts channel change-talk: Watch producer (`agentic_build`) vs
  `irc_agent` formatter.
- Cooldown: keep ~60s per asker for humans; agents may use ~120s poll.

## Gap vs current tree

| Current (#6 / #9) | Wanted |
|---|---|
| `!bobiverse` → DM sequence to asker | Channel chat for humans; `!bobiverse` tray pull for agents (~2 min) |
| Join briefing = DMs | Join may stay DM or become channel hello — prefer not to dump the novel as Query |
| Producer still POINTs (build#36) | No POINT firehose; channel change-talk + tray via pull |
| ionos peer `repo=?` | Real stamp / idle; ionos visible in tray |

## Acceptance

1. A human in Halloy sees conversational status in `#bobiverse`, not as the
   primary Query/DM wall for `!bobiverse`.
2. An agent can `!bobiverse` ~every 2 minutes and refresh tray/peer JSON for
   each fleet id from the answer.
3. Ionos shows up with a non-`?` repo or a clear idle line when Watch is up.
4. Off-DEV tests cover formatter + pull path; no live Ergo required in
   Test-Pack.
5. No secrets. Worker opens a PR; does not stamp UAT.

## Non-goals

- Replacing the tray UI chrome.
- Auto-closing MRB #9 (board of record).
