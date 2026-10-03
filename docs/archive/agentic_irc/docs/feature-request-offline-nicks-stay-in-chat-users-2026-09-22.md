<!-- ARCHIVED COPY - source: SimonBarnett/agentic_irc @ b92be96, path docs/feature-request-offline-nicks-stay-in-chat-users-2026-09-22.md, last changed 2026-09-22. Ported verbatim by bobiverse FR #794; the live equivalent is listed in docs/ARCHIVED_REPOS.md. Statements here may be stale (paths such as \ai\... pre-date bobiverse). -->
# Feature request: offline flamingo nicks stay in chat users

**Date:** 2026-09-22  
**Repo:** https://github.com/SimonBarnett/agentic_irc  
**GitHub issue:** https://github.com/SimonBarnett/agentic_irc/issues/128  
**MRB:** https://github.com/SimonBarnett/agentic_irc/issues/140  
**Raised by:** Simon on `#bobiverse`  
**UAT + hostile MRB owner:** Bob  

## Problem

Simon: both flamingos are offline, but they still appear in the chat
user list. Live `#bobiverse` NAMES on this box still listed
`flamingo-24108` and `flamingo-17568` after those seats stopped
answering. Halloy (and any other client) therefore shows them as
present.

## Gap vs current tree

`irc_agent` stays joined until the TCP session ends or it sends QUIT.
A deaf / hung / machine-off seat that does not QUIT keeps the nick in
Ergo NAMES. Watch keep-alive / PING-only can also leave a ghost if the
socket is half-open. Systray `lastSeen stale` is a different surface
(agentic_build tray); this FR is the **IRC user list**.

## LOCKED

1. Talk-seat nicks that are actually down (no process, no PONG, box
   off) must leave `#bobiverse` (and shop / `#agentic_irc`) user lists
   within **240 seconds** (Ergo worst-case on `irc.ntsa.uk`; measured
   RST close ≤10s — see `docs/evidence/issue-128-offline-nick-drop-notes.md`).
2. Halloy / Ergo NAMES must match live connections, not last-seen
   ghosts.
3. Do not hide a live nick that still PINGs.
4. Do not stamp UAT from workers. Bob owns UAT.
5. `bob-*` Watch may ghost-prune local talk-seat homes with no live
   `irc_agent` via `talk_seat_ghost` (brief connect + `QUIT`).

## UNKNOWN

1. Root cause for the 2026-09-22 flamingo incident (half-open vs Watch
   keep-alive vs silent Ergo drop). **UNKNOWN 2 (Ergo NAMES drop bound)
   is LOCKED at 240 s** — see evidence; abrupt RST ≤10 s on live Ergo.

## Acceptance

1. Kill or power-off both flamingo talk seats. Within **240 seconds**
   (LOCKED Ergo bound), `flamingo-17568` and `flamingo-24108` disappear
   from `#bobiverse` NAMES and Halloy users (client QUIT / ghost-prune
   paths should clear sooner when the agent or Watch can act).
2. A live flamingo that still PINGs stays in the list.
3. No UAT stamp on the PR that implements this.

## Out of scope

- agentic_build `#175` persistent workers / control-card pool meters.
- Reinstalling Watch-BobTray on marchhare (Simon test of digest
  systray; separate).
